"""Find more 豐興 article candidates by scanning multiple listing pages."""
from __future__ import annotations

import asyncio
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


async def main() -> int:
    from bs4 import BeautifulSoup
    from steel_backend.sources.steelnet_client import SteelnetClient

    paths = ["/news.htm", "/news6.htm", "/news.htm?page=2", "/news.htm?page=3"]

    async with SteelnetClient() as sn:
        for p in paths:
            r = await sn._client.get(p)  # type: ignore[union-attr]
            if r.status_code != 200:
                print(f"{p}: HTTP {r.status_code}")
                continue
            soup = BeautifulSoup(r.text, "lxml")
            news_links = []
            for a in soup.find_all("a", href=True):
                if "news-detail" in a["href"]:
                    txt = a.get_text(" ", strip=True)
                    news_links.append((a["href"], txt))
            print(f"{p}: {len(news_links)} news links, "
                  f"{sum('豐興' in t for _, t in news_links)} 豐興")
            for h, t in news_links:
                if "豐興" in t:
                    print(f"   ★ {h:30s}  {t[:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
