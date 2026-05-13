"""Quick dump of history slot values for inspection."""
from __future__ import annotations

import sys
from datetime import date

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


def main() -> int:
    raw = date.fromisoformat(sys.argv[1] if len(sys.argv) > 1 else "2026-05-04")
    from steel_backend.config import get_settings
    from steel_backend.core.dates import opening_monday
    from steel_backend.core.orchestrator import _fill_history_slots
    from steel_backend.storage.sqlite_store import (
        SqliteHistoryStore, get_engine, init_db,
    )
    cfg = get_settings()
    init_db(cfg.database_url)
    store = SqliteHistoryStore(get_engine())
    target = opening_monday(raw)
    sv: dict[str, str] = {}
    cf: dict[str, str] = {}
    _fill_history_slots(sv, cf, store, target)

    print(f"Input date:    {raw}")
    print(f"Opening Monday: {target}")
    print()
    print("Date headers (h6 ← oldest ... h0 → newest):")
    for i in reversed(range(7)):  # print left-to-right (h6 first)
        print(f"  hist_d_h{i} = {sv.get(f'hist_d_h{i}'):>8}")
    for topic in ("sd280", "sd420w", "scrap", "jp2h", "us_container"):
        print(f"\n{topic} history:")
        print("  " + " | ".join(
            f"{sv.get(f'hist_{topic}_h{i}'):>8}" for i in reversed(range(7))
        ))
        print("  " + " | ".join(
            f"{sv.get(f'hist_{topic}_v_h{i}'):>8}" for i in reversed(range(7))
        ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
