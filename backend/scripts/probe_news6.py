"""Probe /news6.htm to understand year/month filter mechanics."""
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

        # 1. GET news6.htm — inspect filter form
        print("[1] GET /news6.htm")
        r = await client.get("/news6.htm")
        print(f"    status={r.status_code} bytes={len(r.text):,}")
        soup = BeautifulSoup(r.text, "lxml")

        # List all forms + their inputs/selects
        forms = soup.find_all("form")
        print(f"    forms: {len(forms)}")
        for i, f in enumerate(forms):
            print(f"    form[{i}] action={f.get('action')!r} method={f.get('method')!r}")
            for inp in f.find_all(["input", "select"]):
                if inp.name == "select":
                    options = [(o.get("value"), o.get_text(" ", strip=True))
                               for o in inp.find_all("option")][:8]
                    print(f"        select name={inp.get('name')!r} options(first 8)={options}")
                else:
                    print(f"        input  name={inp.get('name')!r} type={inp.get('type')!r}"
                          f" value={inp.get('value', '')[:40]!r}")

        # Try a few candidate POST/GET filter URLs
        print()
        print("[2] Try GET /news6.htm?year=2026&month=3&strKey1=豐興")
        r = await client.get("/news6.htm?year=2026&month=3&strKey1=豐興")
        print(f"    status={r.status_code} bytes={len(r.text):,}")

        print()
        print("[3] Try POST /news6.htm with year/month/strKey1")
        # Need fresh csrf
        soup2 = BeautifulSoup(r.text, "lxml")
        csrf_input = soup2.find("input", {"name": "csrf"})
        csrf = csrf_input.get("value", "") if csrf_input else ""
        for payload in [
            {"s_year": "2026", "s_month": "3", "strKey1": "豐興", "csrf": csrf,
             "Class1": "6", "Class2": "6", "this_lang": "1"},
            {"s_year": "2026", "s_month": "3", "strKey1": "豐興", "csrf": csrf},
        ]:
            print(f"    payload keys: {list(payload.keys())}")
            r = await client.post("/news6.htm", data=payload,
                                  headers={"Referer": "https://www.steelnet.com.tw/news6.htm"})
            print(f"      → status={r.status_code} bytes={len(r.text):,}")
            soup3 = BeautifulSoup(r.text, "lxml")
            news_links = [(a["href"], a.get_text(" ", strip=True))
                          for a in soup3.find_all("a", href=True)
                          if "news-detail" in a["href"]]
            fx_links = [(h, t) for h, t in news_links if "豐興" in t]
            mar_links = [(h, t) for h, t in fx_links if "2026/03" in t or "2026/3/" in t]
            print(f"      news-detail links: {len(news_links)}, "
                  f"豐興: {len(fx_links)}, 三月豐興: {len(mar_links)}")
            for h, t in mar_links[:5]:
                print(f"          ★ {h:30s}  {t[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
