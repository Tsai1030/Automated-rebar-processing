"""FastAPI entry point.

Run with:
    uv run uvicorn steel_backend.main:app --reload --port 8001 --host 0.0.0.0
"""
from __future__ import annotations

# IMPORTANT: load_dotenv must run BEFORE any langchain / langsmith /
# openai import. pydantic-settings reads .env into the Settings object
# but does NOT propagate to os.environ — and `langsmith` only checks
# os.environ for LANGCHAIN_TRACING_V2 / LANGCHAIN_API_KEY at import time.
# Without this, traces are silently dropped even though everything else works.
import os
from pathlib import Path
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Importing sources triggers adapter registration via the @register decorator
from . import sources  # noqa: F401
from .api import admin, auth, generation
from .auth.rate_limit import limiter
from .config import get_settings
# Importing each adapter triggers @register decorator
from .sources import fengxing, market_narrator, weekly_market  # noqa: F401
from .storage.sqlite_store import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    cfg = get_settings()
    cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = init_db(cfg.database_url)
    _reap_stranded_runs(engine)
    yield


def _reap_stranded_runs(engine) -> None:  # type: ignore[no-untyped-def]
    """Mark any 'running' generation_runs as 'failed'.

    On free-tier Render the service spins down after 15 min idle, killing
    any in-flight background tasks. Their DB rows would otherwise stay at
    'running' forever, and the frontend would poll until it gave up. Run
    this on every startup to clear the slate. False positives (a task
    that *just* started before a deploy) are acceptable — the user can
    re-trigger.
    """
    from datetime import datetime as _dt
    from sqlmodel import Session as _Session
    from sqlmodel import select as _select

    from .storage.models import GenerationRun

    with _Session(engine) as s:
        stranded = s.exec(
            _select(GenerationRun).where(GenerationRun.status == "running")
        ).all()
        for run in stranded:
            run.status = "failed"
            run.finished_at = _dt.utcnow()
            run.notes = (run.notes or "") + " [reaped on startup]"
            s.add(run)
        if stranded:
            s.commit()


def create_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(
        title="Steel Meeting Auto-fill Backend",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,  # required for HttpOnly cookies
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(generation.router, prefix="/api/generation", tags=["generation"])
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()
