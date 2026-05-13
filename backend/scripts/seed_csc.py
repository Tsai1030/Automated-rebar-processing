"""Seed 中鋼盤價 from the 5/4 PDF — runs once after install.

Run:
    cd backend
    uv run python scripts/seed_csc.py
"""
from __future__ import annotations

import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


# Monthly: (prev_price, change) — order matches MONTHLY_PRODUCTS
_MONTHLY = [
    (31_890, 1_200),
    (36_950, 1_200),
    (33_190, 1_200),
    (35_430, 1_200),
    (34_250, 1_000),
    (34_050, 1_000),
    (39_500, 1_000),
    (38_350, 1_000),
    (35_890, 1_000),
    (40_590, 1_000),
]

# Quarterly: (prev_price, change) — matches QUARTERLY_PRODUCTS
_QUARTERLY = [
    (29_350, 1_000),
    (34_550, 1_000),
    (29_750, 1_000),
    (32_550, 1_000),
    (31_200, 1_000),
    (32_200, 1_000),
    (32_550, 1_000),
    (33_050, 1_000),
    (30_740, 1_000),
    (33_440, 1_000),
    (30_240, 1_000),
    (32_940, 1_000),
    (31_980, 1_000),
    (37_580, 1_000),
    (34_470, 1_000),
    (33_860, 1_000),
]


def main() -> int:
    from steel_backend.config import get_settings
    from steel_backend.core.csc_products import MONTHLY_PRODUCTS, QUARTERLY_PRODUCTS
    from steel_backend.storage.csc_store import write_snapshot
    from steel_backend.storage.sqlite_store import init_db

    cfg = get_settings()
    engine = init_db(cfg.database_url)

    for group, period, ann_date, data, products in [
        ("monthly",   "115 年 5 月份",  "2026/4/15", _MONTHLY,   MONTHLY_PRODUCTS),
        ("quarterly", "115 年第二季",   "2026/3/19", _QUARTERLY, QUARTERLY_PRODUCTS),
    ]:
        rows = [
            {
                "slot_index": i,
                "product_name": products[i],
                "prev_price": prev,
                "change_amount": change,
                "new_price": prev + change,
            }
            for i, (prev, change) in enumerate(data)
        ]
        write_snapshot(
            engine,
            group=group,
            period_label=period,
            announce_date=ann_date,
            rows=rows,  # type: ignore[arg-type]
            updated_by="seed_csc",
        )
        print(f"OK seeded {group}: {len(data)} rows, period={period}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
