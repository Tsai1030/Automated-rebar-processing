"""Abstract storage interfaces.

Why separate abstract from sqlite implementation?
  - Tests use in-memory fakes
  - Stage 3+ could swap to Postgres without touching orchestrator
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from ..sources.base import FetchResult


class HistoryStore(ABC):
    @abstractmethod
    def upsert_price(
        self, result: FetchResult, value_date: date, fetched_by: str
    ) -> None: ...

    @abstractmethod
    def get_latest_before(
        self, slot_key: str, before_date: date
    ) -> FetchResult | None: ...

    @abstractmethod
    def list_history(
        self, slot_key: str, limit: int = 20
    ) -> list[FetchResult]: ...


class UserStore(ABC):
    @abstractmethod
    def get_by_username(self, username: str) -> "UserRecord | None": ...

    @abstractmethod
    def create(
        self, username: str, password_hash: str, role: str = "user"
    ) -> "UserRecord": ...

    @abstractmethod
    def touch_last_login(self, user_id: int) -> None: ...


# Forward-declared DTO so abstract layer can be imported without sqlmodel.
class UserRecord:
    id: int
    username: str
    password_hash: str
    role: str
