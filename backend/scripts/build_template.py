"""Build meeting_template.docx as a 1:1 visual replica of 1150504會議記錄.pdf.

Design principle (per user request, 2026-05-12):
  Layout = exact PDF copy.  We do NOT trim or simplify any section.
  Placeholders = ONLY fields the system can produce. Everything else is
  the literal text from the 5/4 PDF.  Staff opens the Word, sees the
  auto-filled values (豐興 prices, meta, internal form data), and edits
  the rest by hand (盈餘, 中鋼, 七.近期盤價 history, 國際廢鋼, LME, 大陸,
  九.其他市場資訊) directly in Word.

Run with:
    cd backend
    uv run python scripts/build_template.py

Placeholder convention:
  Each `{{slot_key}}` lives in its own run so DocxRenderer can swap it
  cleanly without touching surrounding formatting.
"""
from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

CJK_FONT = "Microsoft JhengHei"
ASCII_FONT = "Calibri"

RED = RGBColor(0xC0, 0x00, 0x00)
BLACK = RGBColor(0x00, 0x00, 0x00)


# ──────────────────────────────────────────────────────────────
# Low-level helpers
# ──────────────────────────────────────────────────────────────

def _bind_cjk(run, size_pt: float | None = None, bold: bool = False,
              color: RGBColor | None = None) -> None:
    """Force a run to use Chinese + ASCII fonts and optional styling."""
    run.font.name = ASCII_FONT
    run.font.bold = bold
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if color is not None:
        run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    existing = rpr.find(qn("w:rFonts"))
    if existing is not None:
        rpr.remove(existing)
    rfonts = rpr.makeelement(qn("w:rFonts"), {
        qn("w:eastAsia"): CJK_FONT,
        qn("w:ascii"): ASCII_FONT,
        qn("w:hAnsi"): ASCII_FONT,
    })
    rpr.append(rfonts)


def add_para(doc_or_cell, parts: list[tuple[str, dict]]) -> None:
    """Add a paragraph from a list of (text, style_dict) tuples.

    style_dict keys: bold, color (RGBColor), size, align (WD_ALIGN_PARAGRAPH).
    """
    p = doc_or_cell.add_paragraph()
    align_set = False
    for text, style in parts:
        if "align" in style and not align_set:
            p.alignment = style["align"]
            align_set = True
        run = p.add_run(text)
        _bind_cjk(
            run,
            size_pt=style.get("size", 11),
            bold=style.get("bold", False),
            color=style.get("color"),
        )


def heading(doc, text: str, size: float = 13, indent: bool = False) -> None:
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.left_indent = Cm(0.5)
    run = p.add_run(text)
    _bind_cjk(run, size_pt=size, bold=True)


def body(doc, text: str, indent_cm: float = 0.0) -> None:
    p = doc.add_paragraph()
    if indent_cm:
        p.paragraph_format.left_indent = Cm(indent_cm)
    run = p.add_run(text)
    _bind_cjk(run, size_pt=11)


def slotted(doc, parts: list, indent_cm: float = 0.0) -> None:
    """Paragraph containing a mix of literal text and {{slot}} placeholders.

    parts entries:
      - str  → literal black text
      - ("ph", "slot_key")  → placeholder run (own run, no special color)
      - ("ph_red", "slot_key")  → placeholder rendered in red
      - ("red", "text")  → literal red text (for 漲跌/價差 inline)
    """
    p = doc.add_paragraph()
    if indent_cm:
        p.paragraph_format.left_indent = Cm(indent_cm)
    for part in parts:
        if isinstance(part, str):
            run = p.add_run(part)
            _bind_cjk(run, size_pt=11)
        elif part[0] == "ph":
            run = p.add_run(f"{{{{{part[1]}}}}}")
            _bind_cjk(run, size_pt=11)
        elif part[0] == "ph_red":
            run = p.add_run(f"{{{{{part[1]}}}}}")
            _bind_cjk(run, size_pt=11, color=RED)
        elif part[0] == "red":
            run = p.add_run(part[1])
            _bind_cjk(run, size_pt=11, color=RED)


def fill_cell(cell, parts, align=WD_ALIGN_PARAGRAPH.CENTER,
              size: float = 11) -> None:
    """Fill a table cell with mixed-content parts (see slotted()).

    Multi-paragraph cells supported: nested list = multiple paragraphs.
    """
    # python-docx default-creates one empty paragraph in each cell
    cell.text = ""
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    def add_one_paragraph(target_para, items):
        target_para.alignment = align
        for item in items:
            if isinstance(item, str):
                run = target_para.add_run(item)
                _bind_cjk(run, size_pt=size)
            elif item[0] == "ph":
                run = target_para.add_run(f"{{{{{item[1]}}}}}")
                _bind_cjk(run, size_pt=size)
            elif item[0] == "ph_red":
                run = target_para.add_run(f"{{{{{item[1]}}}}}")
                _bind_cjk(run, size_pt=size, color=RED)
            elif item[0] == "red":
                run = target_para.add_run(item[1])
                _bind_cjk(run, size_pt=size, color=RED)
            elif item[0] == "bold":
                run = target_para.add_run(item[1])
                _bind_cjk(run, size_pt=size, bold=True)

    # Detect multi-paragraph vs single
    if parts and isinstance(parts[0], list):
        first_p = cell.paragraphs[0]
        add_one_paragraph(first_p, parts[0])
        for extra in parts[1:]:
            add_one_paragraph(cell.add_paragraph(), extra)
    else:
        add_one_paragraph(cell.paragraphs[0], parts)


# ──────────────────────────────────────────────────────────────
# High-level builders
# ──────────────────────────────────────────────────────────────

def add_profit_table(doc, header_row, data_rows, total_row,
                     col_widths_cm=(8.5, 4.5, 4.5)):
    """Build a 三-row 盈餘 table (項目 / 金額 / 備註).

    data_rows: list of tuples (label_text, amount_text_red, note_parts)
    total_row: ("合計...", "x.xx" (red), "") tuple
    """
    n_rows = 1 + len(data_rows) + 1  # header + data + total
    tbl = doc.add_table(rows=n_rows, cols=3)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header
    hdr_cells = tbl.rows[0].cells
    for i, txt in enumerate(header_row):
        fill_cell(hdr_cells[i], [("bold", txt)])

    # Data
    for ri, (label, amount_part, note_parts) in enumerate(data_rows, start=1):
        cells = tbl.rows[ri].cells
        # Label cell (left-aligned)
        fill_cell(cells[0], [label], align=WD_ALIGN_PARAGRAPH.LEFT)
        # Amount cell — red
        fill_cell(cells[1], [amount_part])
        # Note cell
        fill_cell(cells[2], note_parts, size=10)

    # Total row
    t_cells = tbl.rows[-1].cells
    fill_cell(t_cells[0], [("bold", total_row[0])],
              align=WD_ALIGN_PARAGRAPH.LEFT)
    fill_cell(t_cells[1], [total_row[1]])
    fill_cell(t_cells[2], [total_row[2]] if total_row[2] else [""])

    # Column widths
    for col_i, w in enumerate(col_widths_cm):
        for cell in tbl.columns[col_i].cells:
            cell.width = Cm(w)


def add_history_price_table(doc, header_unit_label: str,
                            prices: list[str], deltas: list[str],
                            dates=("3/23", "3/30", "4/7", "4/13",
                                   "4/20", "4/27", "5/4"),
                            last_price_slot: str | None = None,
                            last_delta_slot: str | None = None):
    """Build a 9-col history table for 七.近期盤價 (LITERAL data — Stage 1)."""
    tbl = doc.add_table(rows=3, cols=9)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER

    fill_cell(tbl.rows[0].cells[0], [("bold", "日期")])
    for i, d in enumerate(dates, start=1):
        fill_cell(tbl.rows[0].cells[i], [d])
    fill_cell(tbl.rows[0].cells[8], [("bold", "備註")])

    fill_cell(tbl.rows[1].cells[0], [header_unit_label], size=10)
    for i, p in enumerate(prices, start=1):
        if i == 7 and last_price_slot:
            fill_cell(tbl.rows[1].cells[i], [("ph", last_price_slot)])
        else:
            fill_cell(tbl.rows[1].cells[i], [p])
    fill_cell(tbl.rows[1].cells[8], [""])

    fill_cell(tbl.rows[2].cells[0], [("red", "漲(+)/跌(-)")])
    for i, d in enumerate(deltas, start=1):
        if i == 7 and last_delta_slot:
            fill_cell(tbl.rows[2].cells[i], [("ph_red", last_delta_slot)])
        else:
            fill_cell(tbl.rows[2].cells[i], [("red", d)])
    fill_cell(tbl.rows[2].cells[8], [""])

    widths = [2.3, 1.5, 1.5, 1.4, 1.5, 1.5, 1.5, 1.5, 2.0]
    for col_i, w in enumerate(widths):
        for cell in tbl.columns[col_i].cells:
            cell.width = Cm(w)


def add_dynamic_history_table(doc, header_unit_label: str, topic_key: str):
    """七.1-3 history table — every cell is a {{slot}} placeholder.

    Slots: hist_d_h0..h6 (date headers), hist_<topic>_h0..h6 (price),
    hist_<topic>_v_h0..h6 (delta, red).
    Column order: leftmost = h6 (oldest), rightmost = h0 (newest).
    """
    tbl = doc.add_table(rows=3, cols=9)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header row
    fill_cell(tbl.rows[0].cells[0], [("bold", "日期")])
    for col_i in range(7):
        h_idx = 6 - col_i  # leftmost = h6, rightmost = h0
        fill_cell(tbl.rows[0].cells[col_i + 1], [("ph", f"hist_d_h{h_idx}")])
    fill_cell(tbl.rows[0].cells[8], [("bold", "備註")])

    # Price row
    fill_cell(tbl.rows[1].cells[0], [header_unit_label], size=10)
    for col_i in range(7):
        h_idx = 6 - col_i
        fill_cell(tbl.rows[1].cells[col_i + 1], [("ph", f"hist_{topic_key}_h{h_idx}")])
    fill_cell(tbl.rows[1].cells[8], [""])

    # Delta row (red)
    fill_cell(tbl.rows[2].cells[0], [("red", "漲(+)/跌(-)")])
    for col_i in range(7):
        h_idx = 6 - col_i
        fill_cell(tbl.rows[2].cells[col_i + 1],
                  [("ph_red", f"hist_{topic_key}_v_h{h_idx}")])
    fill_cell(tbl.rows[2].cells[8], [""])

    widths = [2.3, 1.5, 1.5, 1.4, 1.5, 1.5, 1.5, 1.5, 2.0]
    for col_i, w in enumerate(widths):
        for cell in tbl.columns[col_i].cells:
            cell.width = Cm(w)


def add_csc_table(doc, rows):
    """LEGACY: literal 5-col 中鋼盤價 table — kept for any future literal use."""
    tbl = doc.add_table(rows=len(rows) + 1, cols=5)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER

    header = ["產品", "上月基價", "調整金額", "調整後基價", "備註"]
    for i, h in enumerate(header):
        fill_cell(tbl.rows[0].cells[i], [("bold", h)])

    for ri, (product, prev_p, change, new_p, note) in enumerate(rows, start=1):
        cells = tbl.rows[ri].cells
        fill_cell(cells[0], [product], align=WD_ALIGN_PARAGRAPH.LEFT, size=10)
        fill_cell(cells[1], [prev_p])
        fill_cell(cells[2], [("red", change)])
        fill_cell(cells[3], [new_p])
        fill_cell(cells[4], [note] if note else [""])

    widths = [6.5, 2.5, 2.5, 2.8, 1.8]
    for col_i, w in enumerate(widths):
        for cell in tbl.columns[col_i].cells:
            cell.width = Cm(w)


def add_dynamic_csc_table(doc, products: list[str], slot_prefix: str):
    """中鋼盤價 table with {{slot}} placeholders pulling from admin form.

    products: list of product names (10 monthly or 16 quarterly)
    slot_prefix: 'm' for monthly slot keys (csc_m_NN_*) or 'q' for quarterly
    """
    tbl = doc.add_table(rows=len(products) + 1, cols=5)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER

    header = ["產品", "上月基價" if slot_prefix == "m" else "上季基價",
              "調整金額", "調整後基價", "備註"]
    for i, h in enumerate(header):
        fill_cell(tbl.rows[0].cells[i], [("bold", h)])

    for i, product in enumerate(products):
        cells = tbl.rows[i + 1].cells
        fill_cell(cells[0], [product], align=WD_ALIGN_PARAGRAPH.LEFT, size=10)
        fill_cell(cells[1], [("ph", f"csc_{slot_prefix}_{i:02d}_prev")])
        fill_cell(cells[2], [("ph_red", f"csc_{slot_prefix}_{i:02d}_change")])
        fill_cell(cells[3], [("ph", f"csc_{slot_prefix}_{i:02d}_new")])
        fill_cell(cells[4], [""])

    widths = [6.5, 2.5, 2.5, 2.8, 1.8]
    for col_i, w in enumerate(widths):
        for cell in tbl.columns[col_i].cells:
            cell.width = Cm(w)


# ──────────────────────────────────────────────────────────────
# Sections
# ──────────────────────────────────────────────────────────────

def setup_styles(doc):
    normal = doc.styles["Normal"]
    normal.font.name = ASCII_FONT
    normal.font.size = Pt(11)
    rpr = normal.element.get_or_add_rPr()  # type: ignore[attr-defined]
    rfonts = rpr.makeelement(qn("w:rFonts"), {
        qn("w:eastAsia"): CJK_FONT,
        qn("w:ascii"): ASCII_FONT,
        qn("w:hAnsi"): ASCII_FONT,
    })
    rpr.append(rfonts)


def section_title(doc):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("鋼筋研究專案小組會議")
    _bind_cjk(r, size_pt=18, bold=True)
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = p2.add_run("會議記錄")
    _bind_cjk(r2, size_pt=16, bold=True)


def section_one(doc):
    """一、會議時間"""
    slotted(doc, [
        "一、會議時間：",
        ("ph", "meeting_date_roc"),
        " (",
        ("ph", "meeting_weekday"),
        ")",
        ("ph", "meeting_time"),
    ])


def section_two(doc):
    """二、鋼筋採購討論事項"""
    body(doc, "二、鋼筋採購討論事項：")
    heading(doc, "1.上週會議結論及追蹤事項：", size=12)
    slotted(doc, [("ph", "meeting_conclusion_last_week")], indent_cm=0.5)
    heading(doc, "2.本週會議結論：", size=12)
    slotted(doc, [("ph", "meeting_conclusion_this_week")], indent_cm=0.5)
    slotted(doc, [
        "2. 現已採購鋼筋合約之剩餘總量 ",
        ("ph", "contract_remaining_tons"),
        " 噸,可使用至:",
        ("ph", "contract_usable_until"),
        "。",
    ])


def section_three(doc):
    """三、115 年度鋼筋盈餘說明"""
    body(doc, "三、115 年度鋼筋盈餘說明(2.58 億，計 35 個工令)")
    heading(doc, "1. 115 年度(115/3)鋼筋實際盈餘：", size=12, indent=True)
    add_profit_table(
        doc,
        header_row=["項目", "金額(含稅)/單位：億", "備註"],
        data_rows=[
            ("(1)鋼筋標餘款", ("red", "0.34"),
             ["115/1~3", "實際用量標餘款"]),
            ("(2)鋼筋已請領物調款", "1.02",
             ["115/1~3", "已請領物調款"]),
        ],
        total_row=("合計(1)+(2)", "1.36", ""),
    )
    heading(doc, "2. 115 年度(115/3~115/12)鋼筋預估盈餘：", size=12, indent=True)
    add_profit_table(
        doc,
        header_row=["項目", "金額(含稅)/單位：億", "備註"],
        data_rows=[
            ("(1)鋼筋標餘款", ("red", "0.90"),
             ["115/3~115/12", "預估用量標餘款"]),
            ("(2)預估尚需採購鋼筋 4,903 噸盈餘", ("red", "-0.12"),
             [
                 ["依本週豐興開盤預估"],
                 ["SD280：", ("ph", "fx_sd280_price"), " 元"],
                 ["SD420W：", ("ph", "fx_sd420w_price"), " 元"],
             ]),
            ("(3)預估尚可請領鋼筋物調款", "0.43",
             ["依 115/3 物價指數", "(115.60)預估"]),
        ],
        total_row=("合計(1)+(2)+(3)", ("red", "1.22"), ""),
    )


def section_four(doc):
    """四、105/7 開工~121/1 預估鋼筋盈餘說明"""
    body(doc, "四、105/7 開工~121/1(需求截止日)預估鋼筋盈餘說明(0.69 億，計 35 個工令)")
    heading(doc, "1.105/7 開工~115/3 鋼筋實際盈餘：", size=12, indent=True)
    add_profit_table(
        doc,
        header_row=["項目", "金額(含稅)/單位：億", "備註"],
        data_rows=[
            ("(1)鋼筋標餘款", ("red", "-2.42"),
             ["105/7~115/3", "實際用量標餘款"]),
            ("(2)鋼筋已請領物調款", "2.94",
             ["105/1~115/3", "實際用量物調款"]),
        ],
        total_row=("合計(1)+(2)", "0.52", ""),
    )
    heading(doc, "2.115/3~121/1(需求截止日)預估鋼筋盈餘：", size=12, indent=True)
    add_profit_table(
        doc,
        header_row=["項目", "金額(含稅)/單位：億", "備註"],
        data_rows=[
            ("(1)鋼筋標餘款", ("red", "0.91"),
             ["115/3~115/12", "採購標餘款"]),
            ("(2)預估尚需採購鋼筋 158,773 噸盈餘", ("red", "-2.09"),
             [
                 ["依本週豐興開盤預估"],
                 ["SD280：", ("ph", "fx_sd280_price"), " 元"],
                 ["SD420W：", ("ph", "fx_sd420w_price"), " 元"],
             ]),
            ("(3)預估尚可請領鋼筋物調款", "1.35",
             ["依 115/3 物價指數", "(115.60)"]),
        ],
        total_row=("合計(1)+(2)+(3)", ("red", "0.17"), ""),
    )


def section_five(doc):
    """五、105/7 開工~完工採購盈餘"""
    body(doc, "五、105/7 開工~完工採購盈餘(計 35 個工令統計至 115/4/27 止)：")
    add_profit_table(
        doc,
        header_row=["項目", "金額(含稅)/單位：億", "備註"],
        data_rows=[
            ("(1)全部工令標餘款", ("red", "-57.94"), ["不含鋼筋"]),
            ("(2)已採購鋼筋 391,851 噸盈虧", ("red", "-1.51"),
             ["採購使用至 115/12"]),
            ("(3)全部已請領物調款", "63.84", ["含鋼筋", "統計至 115/3"]),
            ("(4)預估尚需採購鋼筋 158,773 噸盈餘", ("red", "-2.09"),
             [
                 ["本週豐興開盤"],
                 ["SD280：", ("ph", "fx_sd280_price"), " 元"],
                 ["SD420W：", ("ph", "fx_sd420w_price"), " 元"],
             ]),
            ("(5)預估尚可請領物調款", "41.57",
             ["含鋼筋", "依 115/3 物價指數", "(115.60)"]),
        ],
        total_row=("合計(1)+(2)+(3)+(4)+(5)", "43.87", ""),
    )
    body(doc, "備註：(4/27 餘 43.18 億、4/20 餘 39.25 億、)")


def section_six(doc):
    """六、相關開盤資訊"""
    body(doc, "六、相關開盤資訊")
    slotted(doc, [
        "1.豐興鋼筋(",
        ("ph", "fengxing_open_date_roc"),
        ")開盤",
    ])
    slotted(doc, [
        "    「豐興」本週廢鋼、鋼筋及型鋼皆維持平盤，鋼筋牌價為 SD280：",
        ("ph", "fx_sd280_price"),
        " 元/噸、SD420W：",
        ("ph", "fx_sd420w_price"),
        " 元/噸，廢鋼基價為 ",
        ("ph", "fx_scrap_base_price"),
        " 元/噸，型鋼牌價為 ",
        ("ph", "fx_section_steel_price"),
        " 元/噸。",
    ])

    # 豐興 table — placeholder for the 4 prices; 價差 stays red literal
    tbl = doc.add_table(rows=5, cols=3)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    header = ["鋼筋規格", "盤價", "價差"]
    for i, h in enumerate(header):
        fill_cell(tbl.rows[0].cells[i], [("bold", h)])
    table_rows = [
        ("SD280", ("ph", "fx_sd280_price"), "+0"),
        ("SD280W", ("ph", "fx_sd280w_price"), "+0"),
        ("SD420", ("ph", "fx_sd420_price"), "+0"),
        ("SD420W", ("ph", "fx_sd420w_price"), "+0"),
    ]
    for ri, (spec, price_ph, diff) in enumerate(table_rows, start=1):
        fill_cell(tbl.rows[ri].cells[0], [spec])
        fill_cell(tbl.rows[ri].cells[1], [price_ph])
        fill_cell(tbl.rows[ri].cells[2], [("red", diff)])
    for col_i, w in enumerate([4, 4, 4]):
        for cell in tbl.columns[col_i].cells:
            cell.width = Cm(w)

    slotted(doc, ["2.", ("ph", "intl_scrap_paragraph")])
    body(doc, "3.大陸方面：")
    slotted(doc, [("ph", "china_xiben_paragraph")], indent_cm=0.5)
    body(doc, "4.國際銅價(倫敦 LME 現貨收盤價)")
    slotted(doc, [("ph", "lme_copper_paragraph")], indent_cm=0.5)


def section_seven(doc):
    """七、近期盤價 — all 5 tables fully dynamic.

    1-3 read from FengxingAdapter persistence (NTD / 元).
    4-5 read from WeeklyMarketAdapter intl scrap numeric extraction (USD / 美元).
    """
    body(doc, "七、近期盤價")

    body(doc, "1.鋼筋 SD280 盤價")
    add_dynamic_history_table(doc, "盤價(元/噸)", "sd280")

    body(doc, "2.鋼筋 SD420W 盤價")
    add_dynamic_history_table(doc, "盤價(元/噸)", "sd420w")

    body(doc, "3.國內廢鋼盤價")
    add_dynamic_history_table(doc, "盤價(元/噸)", "scrap")

    body(doc, "4. 日本 2H 廢鋼盤價")
    add_dynamic_history_table(doc, "盤價(美元/噸)", "jp2h")

    body(doc, "5. 美國貨櫃廢鋼盤價")
    add_dynamic_history_table(doc, "盤價(美元/噸)", "us_container")

    body(doc, "4. 日本 2H 廢鋼盤價")
    add_history_price_table(
        doc,
        header_unit_label="盤價(美元/噸)",
        prices=["350", "未開盤", "未開盤", "370", "375", "385", "385"],
        deltas=["+0", "+0", "+0", "+20", "+5", "+10", "+0"],
    )

    body(doc, "5. 美國貨櫃廢鋼盤價")
    add_history_price_table(
        doc,
        header_unit_label="盤價(美元/噸)",
        prices=["340", "345", "353", "358", "362", "362", "363"],
        deltas=["+7", "+5", "+8", "+5", "+4", "+0", "+1"],
    )


def section_eight(doc):
    """八、中鋼盤價資訊 — fully dynamic, sourced from admin form."""
    from steel_backend.core.csc_products import MONTHLY_PRODUCTS, QUARTERLY_PRODUCTS

    body(doc, "八、中鋼盤價資訊")
    slotted(doc, [
        "1.",
        ("ph", "csc_monthly_period"),
        "月盤鋼品盤價(中鋼發佈日期：",
        ("ph", "csc_monthly_announce_date"),
        ")：　　　　　單位：元/未稅",
    ])
    add_dynamic_csc_table(doc, MONTHLY_PRODUCTS, slot_prefix="m")

    slotted(doc, [
        "2. ",
        ("ph", "csc_quarterly_period"),
        "季盤鋼品盤價(中鋼發佈日期：",
        ("ph", "csc_quarterly_announce_date"),
        ")：　　　　　單位：元/未稅",
    ])
    add_dynamic_csc_table(doc, QUARTERLY_PRODUCTS, slot_prefix="q")


def section_nine(doc):
    """九、其他市場資訊（LLM narrator-generated）"""
    body(doc, "九、其他市場資訊")
    body(doc, "1. 國內資訊：")
    slotted(doc, [("ph", "market_info_domestic")], indent_cm=0.5)
    body(doc, "2. 大陸資訊：")
    slotted(doc, [("ph", "market_info_china")], indent_cm=0.5)


# ──────────────────────────────────────────────────────────────
# Top-level build
# ──────────────────────────────────────────────────────────────

def build():
    doc = Document()
    setup_styles(doc)
    section_title(doc)
    section_one(doc)
    section_two(doc)
    section_three(doc)
    section_four(doc)
    section_five(doc)
    section_six(doc)
    section_seven(doc)
    section_eight(doc)
    section_nine(doc)
    return doc


def main():
    out = Path(__file__).resolve().parent.parent / "templates" / "meeting_template.docx"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = build()
    doc.save(str(out))
    print(f"OK wrote {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
