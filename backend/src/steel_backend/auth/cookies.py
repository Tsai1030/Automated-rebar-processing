"""Helpers for setting / clearing HttpOnly auth cookies."""
from __future__ import annotations

from fastapi import Response

from ..config import get_settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    cfg = get_settings()
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=access,
        httponly=True,
        secure=cfg.COOKIE_SECURE,
        samesite="lax",
        max_age=cfg.JWT_ACCESS_TOKEN_EXPIRE_MIN * 60,
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh,
        httponly=True,
        secure=cfg.COOKIE_SECURE,
        samesite="lax",
        max_age=cfg.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/auth",  # only sent to refresh endpoint
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
