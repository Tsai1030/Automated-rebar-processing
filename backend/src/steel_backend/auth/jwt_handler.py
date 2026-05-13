"""JWT issue + verify."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from ..config import get_settings


class TokenError(Exception):
    """Raised when a token is invalid / expired."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: int, username: str, role: str = "user") -> str:
    cfg = get_settings()
    exp = _now() + timedelta(minutes=cfg.JWT_ACCESS_TOKEN_EXPIRE_MIN)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "type": "access",
        "exp": exp,
        "iat": _now(),
    }
    return jwt.encode(payload, cfg.JWT_SECRET_KEY, algorithm=cfg.JWT_ALGORITHM)


def create_refresh_token(user_id: int, username: str, role: str = "user") -> str:
    cfg = get_settings()
    exp = _now() + timedelta(days=cfg.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "type": "refresh",
        "exp": exp,
        "iat": _now(),
    }
    return jwt.encode(payload, cfg.JWT_SECRET_KEY, algorithm=cfg.JWT_ALGORITHM)


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    cfg = get_settings()
    try:
        payload = jwt.decode(token, cfg.JWT_SECRET_KEY, algorithms=[cfg.JWT_ALGORITHM])
    except JWTError as e:
        raise TokenError(f"Invalid token: {e}") from e
    if payload.get("type") != expected_type:
        raise TokenError(f"Wrong token type: expected {expected_type}")
    return payload
