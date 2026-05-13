"""Shared slowapi limiter — register with FastAPI in main.py."""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Key by client IP. When we have user sessions reliably,
# can switch to a custom key_func that prefers username from cookie.
limiter = Limiter(key_func=get_remote_address, default_limits=[])
