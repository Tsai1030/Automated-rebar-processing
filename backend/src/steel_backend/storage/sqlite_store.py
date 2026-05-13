"""SQLAlchemy-backed implementations of HistoryStore + UserStore.

Despite the module name, the engine here is *not* always SQLite — when
`DATABASE_URL` is set (typically pointing at Neon/Postgres in production)
we use that instead. The module name stays for git history continuity.

SQLite specifics (WAL, busy_timeout PRAGMAs) only run when we're actually
on SQLite. Postgres needs none of that.
"""
from __future__ import annotations

from datetime import date as date_t
from datetime import datetime
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from ..sources.base import FetchResult
from .base import HistoryStore, UserStore
from .models import PriceHistory, User

_engine: Engine | None = None


def _apply_pragmas(dbapi_conn, _connection_record) -> None:  # type: ignore[no-untyped-def]
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def init_db(database_url: str) -> Engine:
    """Open the DB, configure engine for its dialect, run table create +
    any pending lightweight migrations.

    `database_url` is a SQLAlchemy URL (already normalized in
    Settings.database_url). For SQLite we also ensure the parent dir
    exists so a fresh checkout doesn't fail on first run.
    """
    global _engine

    is_sqlite = database_url.startswith("sqlite:")

    if is_sqlite:
        # Extract on-disk path so we can mkdir it. URL is `sqlite:///<path>`
        # — the three slashes mean absolute-ish; SQLAlchemy treats whatever
        # follows the prefix as the file path.
        on_disk = database_url[len("sqlite:///"):]
        if on_disk:
            Path(on_disk).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        event.listen(_engine, "connect", _apply_pragmas)
    else:
        # Postgres (or anything else). pool_pre_ping handles Neon's idle
        # auto-suspend: a stale connection is replaced rather than raising.
        _engine = create_engine(database_url, pool_pre_ping=True)

    SQLModel.metadata.create_all(_engine)
    _apply_lightweight_migrations(_engine)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("DB not initialized — call init_db() first")
    return _engine


def _apply_lightweight_migrations(engine: Engine) -> None:
    """Add columns the ORM expects but legacy DBs lack.

    Using a real migration tool (Alembic) is overkill for a solo app where
    additive column changes are the only shape that ships. Each step is
    idempotent — branched per dialect because SQLite lacks
    `ADD COLUMN IF NOT EXISTS`.
    """
    dialect = engine.dialect.name

    with engine.begin() as conn:
        if dialect == "sqlite":
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
            if "is_active" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
                    )
                )
        elif dialect == "postgresql":
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active "
                    "BOOLEAN NOT NULL DEFAULT TRUE"
                )
            )
        # Other dialects: SQLModel.create_all already produced the right
        # schema for greenfield DBs; if you're migrating an existing DB on
        # an unsupported dialect, add a branch here.


class SqliteHistoryStore(HistoryStore):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def upsert_price(
        self, result: FetchResult, value_date: date_t, fetched_by: str
    ) -> None:
        # Derive the originating source from slot_schema (single source of truth)
        from ..core.slot_schema import SLOTS_BY_KEY
        slot_def = SLOTS_BY_KEY.get(result.slot_key)
        source_name = (slot_def.source if slot_def and slot_def.source else "unknown")
        with Session(self._engine) as s:
            existing = s.exec(
                select(PriceHistory).where(
                    PriceHistory.slot_key == result.slot_key,
                    PriceHistory.value_date == value_date,
                    PriceHistory.source == source_name,
                )
            ).first()
            row = existing or PriceHistory(
                slot_key=result.slot_key,
                value_date=value_date,
                source=source_name,
                fetched_by=fetched_by,
            )
            row.value = result.value
            row.unit = result.unit
            row.raw_text = result.raw_text
            row.source_url = result.source_url
            row.confidence = result.confidence
            row.fetched_at = datetime.utcnow()
            row.fetched_by = fetched_by
            s.add(row)
            s.commit()

    def get_latest_before(
        self, slot_key: str, before_date: date_t
    ) -> FetchResult | None:
        with Session(self._engine) as s:
            row = s.exec(
                select(PriceHistory)
                .where(
                    PriceHistory.slot_key == slot_key,
                    PriceHistory.value_date < before_date,
                )
                .order_by(PriceHistory.value_date.desc())
                .limit(1)
            ).first()
            if row is None:
                return None
            return FetchResult(
                slot_key=row.slot_key,
                value=row.value,
                unit=row.unit or "",
                raw_text=row.raw_text,
                source_url=row.source_url,
                confidence=row.confidence,  # type: ignore[arg-type]
                fetched_at=row.fetched_at.isoformat(),
            )

    def list_recent(
        self, slot_key: str, before_or_on: date_t, count: int = 7
    ) -> list[tuple[date_t, float | None]]:
        """Return up to `count` most recent (date, value) pairs ≤ before_or_on,
        ordered ascending by date (oldest first). Used to populate Section 七."""
        with Session(self._engine) as s:
            rows = s.exec(
                select(PriceHistory)
                .where(
                    PriceHistory.slot_key == slot_key,
                    PriceHistory.value_date <= before_or_on,
                )
                .order_by(PriceHistory.value_date.desc())
                .limit(count)
            ).all()
            pairs = [(r.value_date, r.value) for r in rows]
            return list(reversed(pairs))  # oldest → newest

    def list_history(
        self, slot_key: str, limit: int = 20
    ) -> list[FetchResult]:
        with Session(self._engine) as s:
            rows = s.exec(
                select(PriceHistory)
                .where(PriceHistory.slot_key == slot_key)
                .order_by(PriceHistory.value_date.desc())
                .limit(limit)
            ).all()
            return [
                FetchResult(
                    slot_key=r.slot_key,
                    value=r.value,
                    unit=r.unit or "",
                    raw_text=r.raw_text,
                    source_url=r.source_url,
                    confidence=r.confidence,  # type: ignore[arg-type]
                    fetched_at=r.fetched_at.isoformat(),
                )
                for r in rows
            ]


class SqliteUserStore(UserStore):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_by_username(self, username: str) -> User | None:  # type: ignore[override]
        with Session(self._engine) as s:
            return s.exec(
                select(User).where(User.username == username)
            ).first()

    def create(
        self, username: str, password_hash: str, role: str = "user"
    ) -> User:  # type: ignore[override]
        with Session(self._engine) as s:
            user = User(username=username, password_hash=password_hash, role=role)
            s.add(user)
            s.commit()
            s.refresh(user)
            return user

    def touch_last_login(self, user_id: int) -> None:
        with Session(self._engine) as s:
            user = s.get(User, user_id)
            if user is None:
                return
            user.last_login = datetime.utcnow()
            s.add(user)
            s.commit()
