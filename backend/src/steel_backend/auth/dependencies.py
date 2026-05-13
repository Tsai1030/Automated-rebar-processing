"""FastAPI auth dependencies."""
from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from pydantic import BaseModel

from .cookies import ACCESS_COOKIE
from .jwt_handler import TokenError, decode_token


class CurrentUser(BaseModel):
    id: int
    username: str
    role: str = "user"


async def get_current_user(
    access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
) -> CurrentUser:
    if not access_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_token(access_token, expected_type="access")
    except TokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    return CurrentUser(
        id=int(payload["sub"]),
        username=payload["username"],
        # Legacy tokens issued before role was embedded → treat as "user".
        role=payload.get("role", "user"),
    )


async def require_admin(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user
