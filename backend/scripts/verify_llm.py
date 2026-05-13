"""Smoke-test the OpenAI integration before wiring real adapters.

Run:
    cd backend
    uv run python scripts/verify_llm.py

What it checks (in order, fails fast):
  1. .env loads with OPENAI_API_KEY
  2. The configured OPENAI_MODEL responds to a basic chat completion
  3. The configured model + Responses API + web_search tool work together

If step 3 fails, we know we cannot do real scraping yet — fix before proceeding.
"""
from __future__ import annotations

import asyncio
import sys

# Force UTF-8 stdout on Windows (default cp950 chokes on Chinese / symbols)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from openai import APIError, AsyncOpenAI


async def main() -> int:
    from steel_backend.config import get_settings
    cfg = get_settings()
    print(f"Model:        {cfg.OPENAI_MODEL}")
    print(f"API key tail: ...{cfg.OPENAI_API_KEY[-6:]}")
    print()

    client = AsyncOpenAI(api_key=cfg.OPENAI_API_KEY)

    # ── Test 1: chat.completions ──
    print("[1/3] chat.completions.create — does the model exist?")
    try:
        r = await client.chat.completions.create(
            model=cfg.OPENAI_MODEL,
            messages=[{"role": "user", "content": "Reply with the word OK."}],
            max_completion_tokens=10,
        )
        print(f"     [OK] Reply: {r.choices[0].message.content!r}")
    except APIError as e:
        print(f"     [FAIL] {e.message}")
        return 1

    # ── Test 2: responses.create (basic) ──
    print()
    print("[2/3] responses.create — does the model support Responses API?")
    try:
        r = await client.responses.create(
            model=cfg.OPENAI_MODEL,
            input="Reply with OK.",
        )
        text = getattr(r, "output_text", None) or "(no output_text)"
        print(f"     [OK] Reply: {text[:60]!r}")
    except APIError as e:
        print(f"     [FAIL] {e.message}")
        return 2

    # ── Test 3: responses.create + web_search tool ──
    print()
    print("[3/3] responses.create + web_search tool — does it return citations?")
    try:
        r = await client.responses.create(
            model=cfg.OPENAI_MODEL,
            input=(
                "Search the web for the latest opening price of Feng Hsin Steel "
                "(豐興鋼鐵) SD280 rebar in Taiwan. Reply with one sentence in "
                "Traditional Chinese. Include the source URL."
            ),
            tools=[{"type": "web_search"}],
        )
        text = getattr(r, "output_text", None) or "(no output_text)"
        print(f"     [OK] Reply: {text[:300]}")
    except APIError as e:
        print(f"     [FAIL] {e.message}")
        print(f"     Try changing tool type to 'web_search_preview' if model is older.")
        return 3

    print()
    print("All 3 checks passed. Ready to wire real adapters.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
