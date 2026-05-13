"""Probe steelnet.com.tw login + article structure.

Tries: log in with STEELNET_USER / STEELNET_PASSWORD from .env, fetch the
5/4 article (news-detail10033.htm), and dump useful HTML fragments so we
can design the parser without guessing.

Run:
    cd backend
    uv run python scripts/probe_steelnet.py
    uv run python scripts/probe_steelnet.py news-detail10033.htm    # specific page
    uv run python scripts/probe_steelnet.py --listing                # show news list

We deliberately do NOT echo credentials anywhere. Output goes to stdout
and to data/_probe_steelnet_<page>.html for later inspection.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


async def main() -> int:
    from steel_backend.config import get_settings
    cfg = get_settings()
    if not cfg.STEELNET_USER or not cfg.STEELNET_PASSWORD:
        print("[FAIL] STEELNET_USER / STEELNET_PASSWORD not set in .env")
        return 1

    base = cfg.STEELNET_BASE
    out_dir = cfg.DATA_DIR / "probe"
    out_dir.mkdir(parents=True, exist_ok=True)

    args = sys.argv[1:]
    show_listing = "--listing" in args
    target_page = next(
        (a for a in args if a.endswith(".htm") or a.endswith(".html")),
        "news-detail10033.htm",
    )

    async with httpx.AsyncClient(
        base_url=base,
        timeout=20.0,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
        },
    ) as client:
        # ── 1. GET the real login form (login.htm) ──
        print("[1/4] GET /login.htm")
        r = await client.get("/login.htm")
        login_html = r.text
        print(f"     status={r.status_code}  cookies={list(client.cookies.keys())}")
        (out_dir / "_login_get.html").write_text(login_html, encoding="utf-8")

        soup = BeautifulSoup(login_html, "lxml")
        # Find forms
        forms = soup.find_all("form")
        print(f"     forms on page: {len(forms)}")
        for i, f in enumerate(forms):
            action = f.get("action", "")
            method = f.get("method", "")
            inputs = [
                (inp.get("name"), inp.get("type"), inp.get("value", ""))
                for inp in f.find_all("input")
            ]
            print(f"     form[{i}]: method={method} action={action}")
            for nm, tp, val in inputs:
                preview = (val[:40] + "...") if val and len(val) > 40 else val
                print(f"         input  name={nm!r:30s} type={tp!r:10s} value={preview!r}")

        # ── 2. POST login (use exact field names from form[1]) ──
        print()
        print("[2/4] POST login")
        # Extract csrf from the form we just inspected
        csrf_input = forms[1].find("input", {"name": "csrf"}) if len(forms) > 1 else None
        csrf = csrf_input.get("value", "") if csrf_input else ""
        # The form uses `EMail` (capital E, capital M) for the username field.
        # Per JS: sbForm() sets $("#action").val("ok") then submits form1
        candidate_payloads = [
            {"EMail": cfg.STEELNET_USER, "password": cfg.STEELNET_PASSWORD,
             "action": "ok", "csrf": csrf},
        ]
        login_ok = False
        for payload in candidate_payloads:
            safe_keys = {k: ("***" if "pass" in k.lower() else v) for k, v in payload.items()}
            print(f"     POST /login.htm payload={safe_keys}")
            r = await client.post("/login.htm", data=payload, headers={
                "Referer": f"{base}/login.htm",
                "Origin": base,
            })
            text = r.text
            (out_dir / f"_login_post_{list(payload.keys())[0]}.html").write_text(
                text, encoding="utf-8",
            )
            # Real check: re-fetch homepage and look for 登出 specifically as a
            # link href, not just substring (login.htm appears in templates).
            verify = await client.get("/")
            (out_dir / "_after_login_home.html").write_text(verify.text, encoding="utf-8")
            if 'href="logout.htm"' in verify.text or "登出" in verify.text and "登入" not in verify.text:
                # crude but works once login.htm is replaced by logout.htm in nav
                login_ok = True
                print("     => looks logged in (homepage references logout.htm)")
                break
            # also accept if news-detail returns more than the alert
            test = await client.get("/news-detail10033.htm")
            (out_dir / "_after_login_article.html").write_text(test.text, encoding="utf-8")
            if len(test.text) > 1000 and "非會員只能看標題" not in test.text:
                login_ok = True
                print(f"     => looks logged in (article fetch = {len(test.text):,} bytes)")
                break
            print(f"     => still not logged in. homepage size={len(verify.text)},"
                  f" article size={len(test.text)}")
        if not login_ok:
            print("[FAIL] login payload didn't work")
            return 2

        # ── 2b. Fetch the dedicated 豐興盤價 page ──
        print()
        print("[2b] GET /market_price2.htm (豐興 dedicated price page)")
        r = await client.get("/market_price2.htm")
        mp_text = r.text
        (out_dir / "market_price2.htm").write_text(mp_text, encoding="utf-8")
        print(f"     status={r.status_code}  bytes={len(mp_text):,}")
        mp_soup = BeautifulSoup(mp_text, "lxml")
        for marker in ("SD280", "鋼筋", "豐興", "廢鋼", "型鋼"):
            n = mp_text.count(marker)
            print(f"     '{marker}' occurrences: {n}")
        tables = mp_soup.find_all("table")
        print(f"     tables: {len(tables)}")
        for i, t in enumerate(tables[:3]):
            txt = t.get_text(" | ", strip=True)
            print(f"     table[{i}] preview: {txt[:200]}")

        # ── 3. Fetch the target article ──
        print()
        print(f"[3/4] GET /{target_page}")
        r = await client.get(f"/{target_page}")
        html = r.text
        out_path = out_dir / target_page
        out_path.write_text(html, encoding="utf-8")
        print(f"     status={r.status_code}  bytes={len(html):,}  saved={out_path}")

        soup = BeautifulSoup(html, "lxml")
        title = soup.title.string if soup.title else "(no title)"
        print(f"     <title>: {title!r}")

        # Look for the price table — typically a <table> containing 「SD280」.
        tables = soup.find_all("table")
        print(f"     tables on page: {len(tables)}")
        for i, t in enumerate(tables):
            txt = t.get_text(" ", strip=True)
            if "SD280" in txt or "鋼筋" in txt or "豐興" in txt:
                preview = txt[:200].replace("\n", " ")
                print(f"     table[{i}] (likely relevant): {preview}")

        # Hunt for the paragraph mentioning 美國貨櫃廢鋼 / 日本 2H / 澳洲鐵礦
        body_text = soup.get_text("\n", strip=True)
        for marker in ("美國貨櫃廢鋼", "日本", "澳洲鐵礦", "豐興", "SD280"):
            idx = body_text.find(marker)
            if idx >= 0:
                snippet = body_text[max(0, idx - 30): idx + 150]
                print(f"     '{marker}' found at offset {idx}: ...{snippet}...")
            else:
                print(f"     '{marker}' NOT FOUND")

        # ── 4. If --listing requested, dump the news index too ──
        if show_listing:
            print()
            print("[4/4] GET news listing")
            # Common patterns
            for path in ("/news.htm", "/news_list.htm", "/", "/index.htm"):
                r = await client.get(path)
                if r.status_code == 200 and "news-detail" in r.text:
                    print(f"     listing found at {path} ({len(r.text):,} bytes)")
                    (out_dir / f"_listing_{path.strip('/').replace('/', '_') or 'root'}.html").write_text(
                        r.text, encoding="utf-8",
                    )
                    soup = BeautifulSoup(r.text, "lxml")
                    links = soup.find_all("a", href=True)
                    news_links = [
                        (a.get_text(strip=True), a["href"]) for a in links
                        if "news-detail" in a["href"]
                    ]
                    print(f"     news-detail links: {len(news_links)}")
                    for txt, href in news_links[:10]:
                        print(f"       {href:30s}  {txt[:50]}")
                    break

    print()
    print("Done. Inspect HTML at:", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
