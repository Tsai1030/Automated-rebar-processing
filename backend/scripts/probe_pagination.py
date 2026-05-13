"""Find the right pagination param for /news6.htm filtered listings."""
import asyncio, sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


async def main() -> int:
    from bs4 import BeautifulSoup
    from steel_backend.sources.steelnet_client import SteelnetClient

    async with SteelnetClient() as sn:
        client = sn._client  # type: ignore[union-attr]

        # Filter Jan 2026 豐興, page 1
        r = await client.get("/news6.htm")
        soup = BeautifulSoup(r.text, "lxml")
        csrf = soup.find("input", {"name": "csrf"}).get("value", "")  # type: ignore

        for page in [1, 2, 3, 4]:
            payload = {
                "s_year": "2026", "s_month": "1", "strKey1": "豐興",
                "Class1": "6", "Class2": "6", "this_lang": "1", "csrf": csrf,
                "Page": str(page), "Page2": str(page),
            }
            r = await client.post("/news6.htm", data=payload,
                                  headers={"Referer": "https://www.steelnet.com.tw/news6.htm"})
            soup = BeautifulSoup(r.text, "lxml")
            news_links = [(a["href"], a.get_text(" ", strip=True))
                          for a in soup.find_all("a", href=True)
                          if "news-detail" in a["href"] and "豐興" in a.get_text("", strip=True)]
            # dedupe
            seen = set(); uniq = []
            for h, t in news_links:
                if h not in seen:
                    seen.add(h); uniq.append((h, t))
            print(f"page {page}: {len(uniq)} unique 豐興 articles")
            for h, t in uniq[:6]:
                print(f"   {h:30s}  {t[:70]}")
            print()

        # Also check if pagination links exist in the page
        print("=== Looking for pagination links ===")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if "Page=" in href or text.strip().isdigit():
                print(f"   {text!r:10s}  href={href[:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
