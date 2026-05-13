"""Quick test of parse_intl_scrap_prices on real article samples."""
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from steel_backend.sources.steelnet_client import parse_intl_scrap_prices

SAMPLES = [
    ("5/4 PDF", "本週美國大船廢鋼無報價,美國貨櫃廢鋼上漲1元至363美元/噸,"
                "日本2H廢鋼本週持平為385美元/噸,澳洲鐵礦上漲0.70元至109.75美元/噸。"),
    ("5/4 article", "國際原料行情方面，上週美國大船廢鋼無報價，"
                    "日本H2廢鋼上週沒報價(前週報價上漲10美元至385美元)，"
                    "美國貨櫃廢鋼上週報價微漲1美元至363美元/噸，"
                    "澳洲鐵礦砂上漲0.70美元至109.75美元/噸。"),
    ("1/12 article", "國際原料行情方面，上週美國大船廢鋼無報價，"
                     "日本H2廢鋼報價持平315美元，"
                     "美國貨櫃廢鋼上週報價上漲至305美元/噸(先前為300美元)，"
                     "澳洲鐵礦砂由106.50元/噸上漲至109.20美元/噸。"),
    ("1/26 article", "國際原料行情方面，上週美國大船廢鋼無報價，"
                     "日本H2廢鋼報價上漲2美元至317美元，"
                     "美國貨櫃廢鋼上週報價上漲4美元至312美元/噸，"
                     "澳洲鐵礦砂由106.55元/噸下跌至105.40美元/噸。"),
    ("3/30 case", "國際原料行情方面，上週美國大船廢鋼上漲5美元至370美元，"
                  "日本2H廢鋼未開盤，美國貨櫃廢鋼下跌2美元至355美元/噸。"),
]

for name, s in SAMPLES:
    r = parse_intl_scrap_prices(s)
    us = r["us_container_scrap"]
    jp = r["jp2h_scrap"]
    au = r["au_iron_ore"]
    print(f"[{name}]  US={us}  JP={jp}  AU={au}")
