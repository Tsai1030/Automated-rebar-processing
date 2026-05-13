"""Centralized configuration loaded from env vars.

All tunable values live here — never hardcode URLs / thresholds elsewhere.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = parent of backend/
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_PROJECT_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    """All app config. Loaded from .env at project root (one level above backend/)."""

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ───────────── OpenAI / LangSmith ─────────────
    OPENAI_API_KEY: str = Field(..., description="OpenAI API key (required)")
    OPENAI_MODEL: str = Field(
        default="gpt-5.4-mini",
        description="Model used by LangGraph agents. User-specified.",
    )
    LANGCHAIN_TRACING_V2: bool = True
    LANGCHAIN_API_KEY: str | None = None
    LANGCHAIN_PROJECT: str = "LangGraph-web"

    # ───────────── Auth / JWT ─────────────
    JWT_SECRET_KEY: str = Field(
        default="CHANGE_ME_dev_only_min_32_chars_xxxxxxxx",
        description="HMAC secret for JWT. Must be >=32 chars in production.",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MIN: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = False  # True in production with HTTPS
    # "lax" works when frontend + backend share a site. Cross-site (e.g.
    # frontend on *-frontend.onrender.com calling *-backend.onrender.com,
    # which the PSL treats as cross-site) requires "none" + Secure.
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

    # ───────────── Server / CORS ─────────────
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8001
    FRONTEND_ORIGIN: str = "http://localhost:3001"
    # Add LAN IPs once known, e.g. ["http://localhost:3001", "http://192.168.1.50:3001"]
    EXTRA_CORS_ORIGINS: list[str] = Field(default_factory=list)

    # ───────────── Storage ─────────────
    DATA_DIR: Path = _BACKEND_DIR / "data"
    DB_PATH: Path = _BACKEND_DIR / "data" / "app.db"
    # When set (e.g. "postgresql://user:pass@host/db"), takes priority over
    # DB_PATH. Used in production (Render → Neon Postgres). Leave empty for
    # local dev and SQLite will be used.
    DATABASE_URL: str | None = None
    OUTPUT_DIR: Path = _BACKEND_DIR / "data" / "outputs"
    TEMPLATE_PATH: Path = _BACKEND_DIR / "templates" / "meeting_template.docx"

    # ───────────── Rate limits ─────────────
    RATE_LOGIN_PER_MINUTE: int = 5
    RATE_GENERATE_PER_HOUR: int = 10
    RATE_OPENAI_PER_DAY: int = 30
    RATE_DOWNLOAD_PER_HOUR: int = 20

    # ───────────── Validator thresholds ─────────────
    PRICE_CHANGE_WARN_PCT: float = 5.0  # warn if weekly change >5%
    OPENAI_TOKEN_BUDGET_PER_RUN: int = 50_000

    # ───────────── steelnet.com.tw credentials ─────────────
    # Source for 豐興 weekly opening + intl scrap paragraph.
    # Article is behind member login; we POST to /index.php?action=member_login.
    STEELNET_USER: str = ""
    STEELNET_PASSWORD: str = ""
    STEELNET_BASE: str = "https://www.steelnet.com.tw"

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _check_secret_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return v

    @model_validator(mode="after")
    def _check_samesite_secure(self) -> Settings:
        if self.COOKIE_SAMESITE == "none" and not self.COOKIE_SECURE:
            raise ValueError(
                "COOKIE_SECURE must be True when COOKIE_SAMESITE='none' "
                "(browsers reject SameSite=None without Secure)."
            )
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [self.FRONTEND_ORIGIN, *self.EXTRA_CORS_ORIGINS]

    @property
    def database_url(self) -> str:
        """Resolve the SQLAlchemy URL. Postgres takes priority when set;
        otherwise fall back to SQLite at DB_PATH. The `postgresql://` prefix
        is rewritten to `postgresql+psycopg://` so SQLAlchemy picks psycopg3
        (the version we depend on) instead of the legacy psycopg2."""
        url = self.DATABASE_URL
        if not url:
            return f"sqlite:///{self.DB_PATH}"
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url


_settings: Settings | None = None


def get_settings() -> Settings:
    """Cached settings singleton. Use this via FastAPI dependency."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
