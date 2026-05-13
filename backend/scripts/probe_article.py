"""Inspect a specific article body to understand structure variations."""
import asyncio, sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


async def main() -> int:
    from bs4 import BeautifulSoup
    from steel_backend.sources.steelnet_client import SteelnetClient
    target = sys.argv[1] if len(sys.argv) > 1 else "/news-detail10274.htm"

    async with SteelnetClient() as sn:
        r = await sn._client.get(target)  # type: ignore[union-attr]
        soup = BeautifulSoup(r.text, "lxml")
        text_div = soup.find("div", class_="text")
        if text_div is None:
            print("NO div.text found")
            return 1
        body = text_div.get_text("\n", strip=True)
        print(f"=== {target} body ===")
        print(body[:1500])
        print()
        for marker in ["本週牌價", "鋼筋", "廢鋼", "型鋼", "本週", "牌價", "元"]:
            print(f"   '{marker}' x {body.count(marker)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
