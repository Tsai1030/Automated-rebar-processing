"""Seed price_history with the 7-week table from the 5/4 PDF.

Run once after first install. Idempotent — safe to re-run.

Run:
    cd backend
    uv run python scripts/seed_history.py
"""
from __future__ import annotations

import sys
from datetime import date

# Force UTF-8 stdout on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

# Dates from PDF 七.1-3 tables (Mondays 豐興 opens), plus an extra 3/16
# datum so the leftmost-displayed-column's week-over-week delta is computable.
_DATES = [
    date(2026, 3, 16),  # extra prior week — feeds the 3/23 delta
    date(2026, 3, 23),
    date(2026, 3, 30),
    date(2026, 4, 7),   # Tuesday — 4/6 was a holiday, opening shifted
    date(2026, 4, 13),
    date(2026, 4, 20),
    date(2026, 4, 27),
    date(2026, 5, 4),
]

# Prices per topic, aligned with _DATES order. None = "未開盤" / 無報價.
# 3/16 values back-derived from the +300 / +200 deltas in the PDF.
# Section 七.4 (日本2H) and 七.5 (美國貨櫃) values come from the 5/4 PDF tables.
_HIST = {
    "fx_sd280_price":      [18_000, 18_300, 18_500, 18_700, 18_900, 18_900, 18_900, 18_900],
    "fx_sd420w_price":     [19_000, 19_300, 19_500, 19_700, 19_900, 19_900, 19_900, 19_900],
    "fx_scrap_base_price": [9_000,  9_200,  9_400,  9_600,  9_900,  9_900,  9_900,  9_900],
    # USD/噸; PDF shows 3/30 and 4/7 as 「未開盤」for JP 2H → seed as None
    "intl_jp2h_scrap_price":         [350, 350, None, None, 370, 375, 385, 385],
    "intl_us_container_scrap_price": [333, 340, 345,  353,  358, 362, 362, 363],
}


def main() -> int:
    from sqlmodel import Session, delete

    from steel_backend.config import get_settings
    from steel_backend.sources.base import FetchResult
    from steel_backend.storage.models import PriceHistory
    from steel_backend.storage.sqlite_store import SqliteHistoryStore, init_db
    cfg = get_settings()
    cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine = init_db(cfg.database_url)

    if "--clear" in sys.argv:
        with Session(engine) as s:
            n = s.exec(delete(PriceHistory)).rowcount  # type: ignore[attr-defined]
            s.commit()
        print(f"Cleared {n} existing price_history rows.")

    store = SqliteHistoryStore(engine)
    seeded = 0
    no_quote_rows = 0
    for slot_key, prices in _HIST.items():
        assert len(prices) == len(_DATES)
        unit = "美元/噸" if slot_key.startswith("intl_") else "元/噸"
        for d, p in zip(_DATES, prices):
            # None = "未開盤" — store an explicit row so the date appears in
            # the table with a 未開盤 label, instead of becoming a gap.
            is_no_quote = p is None
            result = FetchResult(
                slot_key=slot_key,
                value=float(p) if not is_no_quote else None,
                unit=unit,
                raw_text=("未開盤" if is_no_quote
                          else "[seeded from 1150504會議記錄.pdf]"),
                source_url="",
                confidence="high",
            )
            store.upsert_price(result, value_date=d, fetched_by="seed_script")
            if is_no_quote:
                no_quote_rows += 1
            else:
                seeded += 1

    print(f"OK seeded {seeded} priced rows + {no_quote_rows} 未開盤 rows "
          f"for {len(_HIST)} topics × {len(_DATES)} dates")
    print(f"DB: {cfg.DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
