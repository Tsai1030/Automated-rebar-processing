"""Auth endpoints: login, logout, me, refresh."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from ..auth.cookies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
)
from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.jwt_handler import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from ..auth.password import verify_password
from ..auth.rate_limit import limiter
from ..config import get_settings
from ..storage.sqlite_store import SqliteUserStore, get_engine
from .schemas import LoginRequest, LoginResponse, UserResponse

router = APIRouter()


def _user_store() -> SqliteUserStore:
    return SqliteUserStore(get_engine())


@router.post("/login", response_model=LoginResponse)
@limiter.limit(lambda: f"{get_settings().RATE_LOGIN_PER_MINUTE}/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
) -> LoginResponse:
    store = _user_store()
    user = store.get_by_username(body.username)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    assert user.id is not None
    store.touch_last_login(user.id)

    access = create_access_token(user.id, user.username)
    refresh = create_refresh_token(user.id, user.username)
    set_auth_cookies(response, access, refresh)
    return LoginResponse(
        user=UserResponse(id=user.id, username=user.username, role=user.role)
    )


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
async def me(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> UserResponse:
    store = _user_store()
    db_user = store.get_by_username(user.username)
    if db_user is None or db_user.id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return UserResponse(id=db_user.id, username=db_user.username, role=db_user.role)


@router.post("/refresh")
@limiter.limit("10/minute")
async def refresh(
    request: Request,
    response: Response,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> dict[str, bool]:
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    user_id = int(payload["sub"])
    username = payload["username"]
    new_access = create_access_token(user_id, username)
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=new_access,
        httponly=True,
        secure=get_settings().COOKIE_SECURE,
        samesite="lax",
        max_age=get_settings().JWT_ACCESS_TOKEN_EXPIRE_MIN * 60,
        path="/",
    )
    return {"ok": True}
