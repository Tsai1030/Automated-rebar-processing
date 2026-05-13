"""End-to-end orchestrator smoke test.

Runs the LangGraph workflow once for a target date and prints what slot values
came back from each source. Useful to validate Stage 1-B without booting the
full HTTP stack.

Run:
    cd backend
    uv run python scripts/smoke_orchestrator.py 2026-05-04
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date

# Force UTF-8 stdout on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


async def main() -> int:
    target = date.fromisoformat(sys.argv[1] if len(sys.argv) > 1 else "2026-05-04")
    print(f"Target date: {target.isoformat()}")
    print()

    # Importing here ensures all adapters self-register
    from steel_backend.config import get_settings
    from steel_backend.core.orchestrator import get_graph
    from steel_backend.sources import fengxing, market_narrator, weekly_market  # noqa: F401
    from steel_backend.storage.sqlite_store import init_db

    cfg = get_settings()
    cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    init_db(cfg.database_url)

    graph = get_graph()
    state = await graph.ainvoke({
        "run_id": -1,                       # not persisted
        "meeting_date": target,
        "fengxing_open_date": target,
        "started_by": "smoke",
        "internal_data": {
            "meeting_time": "17:00~17:30",
            "contract_remaining_tons": "57,198",
            "contract_usable_until": "116 年 1 月",
            "meeting_conclusion_last_week": "（測試）",
            "meeting_conclusion_this_week": "（測試）",
        },
        "retry_count": 0,
        "max_retries": 1,
    })

    # Print fetched values
    print("Fetched results:")
    for r in state.get("validated", []):
        v = r.value if r.value is not None else "—"
        snippet = (r.raw_text or "")[:80].replace("\n", " ")
        print(f"  {r.slot_key:32s} = {v!s:>14}  [{r.confidence}]  {snippet}")

    # TEXT narratives — show full text
    print()
    print("LLM-generated paragraphs:")
    for key in (
        "intl_scrap_paragraph", "china_xiben_paragraph", "lme_copper_paragraph",
        "market_info_domestic", "market_info_china",
    ):
        text = state["slot_values"].get(key, "")
        print(f"\n--- {key} ---\n{text}")

    print()
    print(f"Output Word: {state.get('output_path')}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
