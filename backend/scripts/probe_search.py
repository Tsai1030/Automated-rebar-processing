"""Try the site search to find 豐興 articles."""
from __future__ import annotations

import asyncio
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


async def main() -> int:
    from bs4 import BeautifulSoup
    from steel_backend.sources.steelnet_client import SteelnetClient

    async with SteelnetClient() as sn:
        client = sn._client  # type: ignore[union-attr]

        # Need a fresh csrf token
        r = await client.get("/")
        soup = BeautifulSoup(r.text, "lxml")
        csrf_input = soup.find("input", {"name": "csrf"})
        csrf = csrf_input.get("value", "") if csrf_input else ""
        print(f"csrf={csrf[:20]}…")

        # Try search via POST
        r = await client.post(
            "/search.htm",
            data={"strKey1": "豐興", "csrf": csrf},
            headers={"Referer": "https://www.steelnet.com.tw/"},
        )
        print(f"POST /search.htm → {r.status_code}, {len(r.text)} bytes")
        soup = BeautifulSoup(r.text, "lxml")
        links = []
        for a in soup.find_all("a", href=True):
            if "news-detail" in a["href"]:
                links.append((a["href"], a.get_text(" ", strip=True)))
        print(f"news-detail links: {len(links)}")
        for h, t in links[:15]:
            print(f"  {h:30s}  {t[:60]}")

        # Also try GET
        print()
        r = await client.get("/search.htm?strKey1=豐興")
        print(f"GET /search.htm?strKey1=豐興 → {r.status_code}, {len(r.text)} bytes")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
