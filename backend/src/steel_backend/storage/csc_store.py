"""CRUD helpers for 中鋼盤價 state.

Two-tier design:
  - CscPriceState: 26 rows (10 monthly + 16 quarterly) carrying the
    "current" prices. Updated by admin form.
  - CscAnnouncementMeta: 2 rows (one per group) carrying period label +
    announce date displayed in the section headers.

We treat both as state, not history — admin overwrites in place. Audit
trail can be reconstructed from `updated_at` + `updated_by`.
"""
from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from ..core.csc_products import MONTHLY_PRODUCTS, QUARTERLY_PRODUCTS
from .models import CscAnnouncementMeta, CscPriceState


class CscRowDto(TypedDict):
    slot_index: int
    product_name: str
    prev_price: int
    change_amount: int
    new_price: int  # computed: prev + change


class CscGroupSnapshot(TypedDict):
    group: str
    period_label: str
    announce_date: str
    rows: list[CscRowDto]


def _products_for(group: str) -> list[str]:
    return MONTHLY_PRODUCTS if group == "monthly" else QUARTERLY_PRODUCTS


def read_snapshot(engine: Engine, group: str) -> CscGroupSnapshot:
    """Return all current rows for one group, ordered by slot_index."""
    with Session(engine) as s:
        meta = s.get(CscAnnouncementMeta, group)
        rows_db = s.exec(
            select(CscPriceState)
            .where(CscPriceState.group == group)
            .order_by(CscPriceState.slot_index)
        ).all()

    by_idx: dict[int, CscPriceState] = {r.slot_index: r for r in rows_db}
    products = _products_for(group)
    rows: list[CscRowDto] = []
    for i, name in enumerate(products):
        r = by_idx.get(i)
        prev = r.prev_price if r else 0
        change = r.change_amount if r else 0
        rows.append({
            "slot_index": i,
            "product_name": name,
            "prev_price": prev,
            "change_amount": change,
            "new_price": prev + change,
        })

    return {
        "group": group,
        "period_label": meta.period_label if meta else "",
        "announce_date": meta.announce_date if meta else "",
        "rows": rows,
    }


def write_snapshot(
    engine: Engine,
    *,
    group: str,
    period_label: str,
    announce_date: str,
    rows: list[CscRowDto],
    updated_by: str,
) -> None:
    """Overwrite one group's 26 rows + metadata in a single transaction."""
    products = _products_for(group)
    if len(rows) != len(products):
        raise ValueError(
            f"group={group} expects {len(products)} rows, got {len(rows)}"
        )

    now = datetime.utcnow()
    with Session(engine) as s:
        meta = s.get(CscAnnouncementMeta, group)
        if meta is None:
            meta = CscAnnouncementMeta(group=group)
        meta.period_label = period_label
        meta.announce_date = announce_date
        meta.updated_at = now
        meta.updated_by = updated_by
        s.add(meta)

        for r in rows:
            idx = r["slot_index"]
            existing = s.exec(
                select(CscPriceState).where(
                    CscPriceState.group == group,
                    CscPriceState.slot_index == idx,
                )
            ).first()
            row = existing or CscPriceState(group=group, slot_index=idx)
            row.prev_price = int(r["prev_price"])
            row.change_amount = int(r["change_amount"])
            row.updated_at = now
            row.updated_by = updated_by
            s.add(row)

        s.commit()
