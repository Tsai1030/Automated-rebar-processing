"""Smoke test the FengxingFinderAgent end-to-end.

Run:
    cd backend
    uv run python scripts/smoke_steelnet.py 2026-03-16   # any Monday
    uv run python scripts/smoke_steelnet.py              # defaults to today
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

# Show INFO logs from the agent
logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")


async def main() -> int:
    from steel_backend.sources.fengxing import FengxingAdapter
    from steel_backend.sources.fengxing_finder import find_article

    target = (
        date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    )
    print(f"=== target_date = {target} ===")
    print()

    print("[A] FengxingFinderAgent.find_article()")
    parsed, picked, trace = await find_article(target)
    print()
    print("--- TRACE ---")
    for line in trace:
        print(f"   {line}")
    print()
    print(f"--- RESULT ---")
    if picked:
        print(f"   url   : {picked['url']}")
        print(f"   title : {picked['title']}")
    else:
        print("   picked: None")
    print(f"   parsed: {parsed}")
    if parsed:
        print(f"   opening_paragraph: {parsed.opening_paragraph[:200]}")
        if parsed.intl_scrap_paragraph:
            print(f"   intl_paragraph:   {parsed.intl_scrap_paragraph[:200]}")
    print()

    # End-to-end via adapter
    print("[B] FengxingAdapter.fetch()")
    adapter = FengxingAdapter()
    results = await adapter.fetch(target)
    for r in results:
        v = f"{int(r.value):,}" if r.value is not None else "—"
        print(f"   {r.slot_key:28s} = {v:>10}  [{r.confidence}]")
    if results:
        print()
        print(f"   raw_text on first slot:")
        print(f"   {results[0].raw_text}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
