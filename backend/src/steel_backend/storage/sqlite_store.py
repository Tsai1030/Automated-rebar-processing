"""SQLite-backed implementations of HistoryStore + UserStore.

Critical: WAL mode is enabled on every connection. SQLite default is rollback
journal, which serializes reads against writers — WAL gives us concurrent reads
during writes, which matters when one user is generating while others browse
history.
"""
from __future__ import annotations

from datetime import date as date_t
from datetime import datetime
from pathlib import Path

from sqlalchemy import event
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


def init_db(path: Path) -> Engine:
    """Open the SQLite db, enable WAL, create tables if missing."""
    global _engine
    path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )
    event.listen(_engine, "connect", _apply_pragmas)
    SQLModel.metadata.create_all(_engine)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("DB not initialized — call init_db() first")
    return _engine


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
