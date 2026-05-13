"""Admin endpoints — bootstrap + CSC price table management + user admin."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from ..auth.dependencies import CurrentUser, get_current_user, require_admin
from ..auth.password import hash_password
from ..core.csc_products import MONTHLY_PRODUCTS, QUARTERLY_PRODUCTS
from ..storage.csc_store import CscRowDto, read_snapshot, write_snapshot
from ..storage.models import GenerationRun, User
from ..storage.sqlite_store import get_engine

router = APIRouter()


# Allowed group values keep mistypes from creating ghost groups
GroupName = Literal["monthly", "quarterly"]

# Hardcoded one-time setup secret. Change in .env for production.
_BOOTSTRAP_SECRET = "first_run_setup"


@router.post("/bootstrap")
async def bootstrap_admin(
    username: str = Query(..., min_length=3, max_length=64),
    password: str = Query(..., min_length=8, max_length=256),
    secret: str = Query(...),
) -> dict[str, str]:
    """Create the first admin. Refuses if any user already exists."""
    if secret != _BOOTSTRAP_SECRET:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bad bootstrap secret")
    engine = get_engine()
    with Session(engine) as s:
        existing = s.exec(select(User)).first()
        if existing is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Users already exist — bootstrap is one-shot",
            )
        user = User(
            username=username,
            password_hash=hash_password(password),
            role="admin",
        )
        s.add(user)
        s.commit()
    return {"status": "created", "username": username}


# ──────────────────────────────────────────────────────────────
# 中鋼盤價 admin
# ──────────────────────────────────────────────────────────────

class CscRowIn(BaseModel):
    slot_index: int = Field(ge=0)
    prev_price: int = 0
    change_amount: int = 0


class CscSaveRequest(BaseModel):
    period_label: str = ""
    announce_date: str = ""
    rows: list[CscRowIn]


@router.get("/csc/{group}")
async def get_csc(
    group: GroupName,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    _ = user  # any logged-in user can read CSC tables
    snap = read_snapshot(get_engine(), group)
    return snap


@router.put("/csc/{group}")
async def put_csc(
    group: GroupName,
    body: CscSaveRequest,
    user: Annotated[CurrentUser, Depends(require_admin)],
) -> dict[str, str]:
    products = MONTHLY_PRODUCTS if group == "monthly" else QUARTERLY_PRODUCTS
    if len(body.rows) != len(products):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"group={group} expects {len(products)} rows, got {len(body.rows)}",
        )
    # Convert pydantic → typed dict; product_name + new_price are derived.
    rows: list[CscRowDto] = []
    for i, r in enumerate(body.rows):
        if r.slot_index != i:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"row {i} has slot_index={r.slot_index}, expected {i}",
            )
        rows.append({
            "slot_index": i,
            "product_name": products[i],
            "prev_price": r.prev_price,
            "change_amount": r.change_amount,
            "new_price": r.prev_price + r.change_amount,
        })
    write_snapshot(
        get_engine(),
        group=group,
        period_label=body.period_label,
        announce_date=body.announce_date,
        rows=rows,
        updated_by=user.username,
    )
    return {"status": "ok"}


# ──────────────────────────────────────────────────────────────
# User management (admin only)
# ──────────────────────────────────────────────────────────────

class AdminUserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime
    last_login: datetime | None


class CreateUserIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    role: Literal["admin", "user"] = "user"


class UpdateUserIn(BaseModel):
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None


class ResetPasswordIn(BaseModel):
    password: str = Field(min_length=8, max_length=256)


def _user_to_out(u: User) -> AdminUserOut:
    assert u.id is not None
    return AdminUserOut(
        id=u.id,
        username=u.username,
        role=u.role,
        is_active=u.is_active,
        created_at=u.created_at,
        last_login=u.last_login,
    )


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    _admin: Annotated[CurrentUser, Depends(require_admin)],
) -> list[AdminUserOut]:
    with Session(get_engine()) as s:
        rows = s.exec(select(User).order_by(User.created_at.asc())).all()
        return [_user_to_out(u) for u in rows]


@router.post("/users", response_model=AdminUserOut, status_code=201)
async def create_user(
    body: CreateUserIn,
    _admin: Annotated[CurrentUser, Depends(require_admin)],
) -> AdminUserOut:
    with Session(get_engine()) as s:
        existing = s.exec(select(User).where(User.username == body.username)).first()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")
        user = User(
            username=body.username,
            password_hash=hash_password(body.password),
            role=body.role,
            is_active=True,
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        return _user_to_out(user)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: int,
    body: UpdateUserIn,
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> AdminUserOut:
    with Session(get_engine()) as s:
        user = s.get(User, user_id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        # Prevent admins from locking themselves out by demoting / disabling self.
        if user.id == admin.id:
            if body.role is not None and body.role != "admin":
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "You cannot demote your own admin account",
                )
            if body.is_active is False:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "You cannot disable your own account",
                )
        if body.role is not None:
            user.role = body.role
        if body.is_active is not None:
            user.is_active = body.is_active
        s.add(user)
        s.commit()
        s.refresh(user)
        return _user_to_out(user)


@router.post("/users/{user_id}/password")
async def reset_password(
    user_id: int,
    body: ResetPasswordIn,
    _admin: Annotated[CurrentUser, Depends(require_admin)],
) -> dict[str, str]:
    with Session(get_engine()) as s:
        user = s.get(User, user_id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        user.password_hash = hash_password(body.password)
        s.add(user)
        s.commit()
    return {"status": "ok"}


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> None:
    if user_id == admin.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "You cannot delete your own account"
        )
    with Session(get_engine()) as s:
        user = s.get(User, user_id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        s.delete(user)
        s.commit()
    return None


# ──────────────────────────────────────────────────────────────
# Usage stats (admin only)
# ──────────────────────────────────────────────────────────────

class UsageRow(BaseModel):
    username: str
    runs_total: int
    runs_success: int
    runs_failed: int
    last_run_at: datetime | None


@router.get("/usage", response_model=list[UsageRow])
async def usage_stats(
    _admin: Annotated[CurrentUser, Depends(require_admin)],
) -> list[UsageRow]:
    """Per-user counts pulled from generation_runs. Cheap enough for solo
    use to compute on each request — swap to a materialised table only if
    the run table grows past ~100k rows."""
    with Session(get_engine()) as s:
        stmt = (
            select(
                GenerationRun.started_by,
                func.count(GenerationRun.id).label("total"),
                func.sum(
                    func.iif(GenerationRun.status == "success", 1, 0)
                ).label("success"),
                func.sum(
                    func.iif(GenerationRun.status == "failed", 1, 0)
                ).label("failed"),
                func.max(GenerationRun.started_at).label("last_run"),
            )
            .group_by(GenerationRun.started_by)
            .order_by(func.max(GenerationRun.started_at).desc())
        )
        rows = s.exec(stmt).all()
        return [
            UsageRow(
                username=r[0],
                runs_total=int(r[1] or 0),
                runs_success=int(r[2] or 0),
                runs_failed=int(r[3] or 0),
                last_run_at=r[4],
            )
            for r in rows
        ]
