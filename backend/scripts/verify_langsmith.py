"""Tiny test that fires one @traceable call and checks if LangSmith stores it.

Run:
    cd backend
    uv run python scripts/verify_langsmith.py
"""
from __future__ import annotations

import asyncio
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


async def main() -> int:
    # Load env BEFORE importing langsmith / steel_backend
    from dotenv import load_dotenv
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    load_dotenv(os.path.join(project_root, ".env"))

    print("=== Env check ===")
    for key in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_PROJECT"):
        print(f"   {key} = {os.getenv(key)}")
    api_key = os.getenv("LANGCHAIN_API_KEY", "")
    print(f"   LANGCHAIN_API_KEY tail = ...{api_key[-6:]}  (len={len(api_key)})")
    print(f"   LANGSMITH_API_KEY tail = ...{os.getenv('LANGSMITH_API_KEY', '')[-6:]}")
    print()

    if not api_key:
        print("[FAIL] no LANGCHAIN_API_KEY — traces will be silently dropped")
        return 1

    from langsmith import Client, traceable

    @traceable(run_type="chain", name="verify_langsmith.demo")
    def demo_function(x: int) -> dict:
        return {"input": x, "doubled": x * 2}

    @traceable(run_type="llm", name="verify_langsmith.fake_llm")
    async def fake_llm(prompt: str) -> str:
        await asyncio.sleep(0.01)
        return f"echo: {prompt}"

    print("=== Firing 2 traces ===")
    r1 = demo_function(7)
    print(f"   demo_function(7) = {r1}")
    r2 = await fake_llm("hello")
    print(f"   fake_llm('hello') = {r2}")
    print()

    # Wait for the background uploader to flush
    print("=== Flushing trace queue ===")
    client = Client()
    # langsmith uses a background thread; give it time
    await asyncio.sleep(3)

    # Try to query recent runs to see if our traces landed
    print("=== Recent runs in project ===")
    project = os.getenv("LANGCHAIN_PROJECT", "default")
    try:
        runs = list(client.list_runs(project_name=project, limit=5))
        if not runs:
            print(f"   [WARN] no runs in project '{project}'")
            print("   Possible causes:")
            print("     - API key invalid / wrong workspace")
            print("     - Project name typo (case-sensitive)")
            print("     - Trace queue still flushing (try waiting 30s and refresh UI)")
        for r in runs:
            print(f"   • {r.name:40s}  start={r.start_time}  status={r.status}")
        print()
        print(f"Open https://smith.langchain.com/o/_/projects/p/{project}")
        print("(or use UI search to find the project)")
    except Exception as e:
        print(f"   [FAIL] list_runs error: {type(e).__name__}: {e}")
        print("   This usually means the API key has no access to the project.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
