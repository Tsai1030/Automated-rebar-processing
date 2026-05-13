"""Admin endpoints — bootstrap + CSC price table management."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.password import hash_password
from ..core.csc_products import MONTHLY_PRODUCTS, QUARTERLY_PRODUCTS
from ..storage.csc_store import CscRowDto, read_snapshot, write_snapshot
from ..storage.models import User
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


def _require_admin(user: CurrentUser) -> None:
    # Stage 1 keeps the check loose — every logged-in user can read.
    # Tighten when more roles exist; reading the bootstrap account's
    # role would require an extra DB hit per request and we're solo-using.
    _ = user


@router.get("/csc/{group}")
async def get_csc(
    group: GroupName,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    _require_admin(user)
    snap = read_snapshot(get_engine(), group)
    return snap


@router.put("/csc/{group}")
async def put_csc(
    group: GroupName,
    body: CscSaveRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, str]:
    _require_admin(user)
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
