"""LangGraph orchestrator — wires fetch → validate → narrate → render.

Graph topology:

        ┌─────────┐
        │  fetch  │  (parallel calls to each SourceAdapter)
        └────┬────┘
             ▼
        ┌──────────┐
        │ validate │
        └────┬─────┘
             ▼
        ┌──────────┐
        │ narrate  │  (build slot_values dict, generate paragraph strings)
        └────┬─────┘
             ▼
        ┌──────────┐
        │  render  │  (write Word file via DocxRenderer)
        └──────────┘

Stage 1+ will add:
  - real fetching via LangGraph agents using web_search
  - multi-source cross-validation
  - rich narrator templates with LLM
  - retry-on-validation-fail edge from validate → fetch
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from ..config import get_settings
from ..output.docx_renderer import DocxRenderer
from ..sources.base import get_adapter
from ..storage.sqlite_store import SqliteHistoryStore, get_engine
from .dates import opening_monday
from .graph_state import GenerationState
from .slot_schema import HISTORY_TOPICS, SLOTS, SLOTS_BY_KEY, SlotType


def _format_roc_date(d: date) -> str:
    """ISO date → 民國 format e.g. 2026-05-04 → '115/5/4'."""
    roc_year = d.year - 1911
    return f"{roc_year}/{d.month}/{d.day}"


def _format_roc_md(d: date) -> str:
    return f"{d.month}/{d.day}"


async def _node_fetch(state: GenerationState) -> dict:
    """Call every distinct source adapter referenced by an auto-fillable slot."""
    fengxing_date = state.get("fengxing_open_date") or state["meeting_date"]
    source_names = {
        s.source for s in SLOTS_BY_KEY.values() if s.source and s.auto_fillable
    }
    results = []
    for name in source_names:
        adapter_cls = get_adapter(name)
        adapter = adapter_cls()
        results.extend(await adapter.fetch(fengxing_date))
    return {"fetched": results}


def _node_validate(state: GenerationState) -> dict:
    """Stage 1: flag any missing-but-expected value as a 'warn' issue."""
    issues = []
    validated = []
    for r in state.get("fetched", []):
        if r.value is None:
            issues.append({
                "slot_key": r.slot_key,
                "severity": "warn",
                "message": f"no value (confidence={r.confidence})",
            })
        validated.append(r)
    return {"validated": validated, "issues": issues}


def _node_persist(state: GenerationState) -> dict:
    """Write all numeric fetched results to price_history.

    Always keys rows by the *opening Monday* (not the user-selected meeting
    date). 豐興 only opens on Mondays, so persisting Tuesday/Wednesday rows
    would create gaps in 七.近期盤價.

    Why a separate node? Idempotency: if narrate or render fails we still
    have the data; if validation flags problems we still record what we got
    (with low confidence) so future runs can backfill / detect drift.
    """
    try:
        store = SqliteHistoryStore(get_engine())
    except RuntimeError:
        return {}  # DB not initialized in some smoke contexts
    user = state.get("started_by", "system")
    raw_d = state.get("fengxing_open_date") or state["meeting_date"]
    monday = opening_monday(raw_d)
    for r in state.get("validated", []):
        if r.value is None:
            continue  # don't pollute history with nulls
        store.upsert_price(r, monday, user)
    return {}


def _node_narrate(state: GenerationState) -> dict:
    """Build {slot_key: rendered_string} from validated results + metadata.

    Also derives the meeting metadata slots from inputs.
    """
    slot_values: dict[str, str] = {}
    confidence: dict[str, str] = {}

    # ── 1. metadata slots ──
    meeting_d: date = state["meeting_date"]
    fengxing_d: date = state.get("fengxing_open_date") or meeting_d
    _WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]
    slot_values["meeting_date"] = meeting_d.isoformat()
    slot_values["meeting_date_roc"] = _format_roc_date(meeting_d)
    slot_values["meeting_weekday"] = _WEEKDAY_CN[meeting_d.weekday()]
    slot_values["meeting_time"] = ""  # supplied by internal_data merge step
    slot_values["fengxing_open_date_roc"] = _format_roc_md(fengxing_d)
    for k in ("meeting_date", "meeting_date_roc", "meeting_weekday",
              "meeting_time", "fengxing_open_date_roc"):
        confidence[k] = "high"

    # ── 2. fetched values ──
    for r in state.get("validated", []):
        slot_def = SLOTS_BY_KEY.get(r.slot_key)
        # TEXT slots carry the rendered string in raw_text (value is None)
        if slot_def and slot_def.type == SlotType.TEXT:
            text = (r.raw_text or "").strip()
            slot_values[r.slot_key] = text if text else "—"
        elif r.value is None:
            slot_values[r.slot_key] = "—"
        elif slot_def and slot_def.type == SlotType.PRICE:
            slot_values[r.slot_key] = f"{int(r.value):,}"
        else:
            slot_values[r.slot_key] = str(r.value)
        confidence[r.slot_key] = r.confidence

    # ── 3. internal slots default to '—' (overridden by internal-data POST) ──
    for s in SLOTS:
        if not s.auto_fillable and s.key not in slot_values:
            slot_values[s.key] = "—"
            confidence[s.key] = "low"

    # ── 4. apply any internal data supplied during this run ──
    for k, v in state.get("internal_data", {}).items():
        slot_values[k] = str(v)
        confidence[k] = "high"

    # ── 5. Section 七 history tables (read from price_history) ──
    # Always look up against the opening Monday so the rightmost column
    # of the displayed history matches the week 豐興 actually opened.
    try:
        store = SqliteHistoryStore(get_engine())
    except RuntimeError:
        store = None
    if store is not None:
        _fill_history_slots(slot_values, confidence, store, opening_monday(meeting_d))

    # ── 6. Section 八 中鋼盤價 (read from CscPriceState admin table) ──
    try:
        _fill_csc_slots(slot_values, confidence)
    except RuntimeError:
        pass

    return {"slot_values": slot_values, "confidence": confidence}


def _fill_csc_slots(
    slot_values: dict[str, str],
    confidence: dict[str, str],
) -> None:
    """Read both 中鋼 groups from DB and stuff their values into slot_values."""
    from ..storage.csc_store import read_snapshot

    engine = get_engine()
    for group, prefix in (("monthly", "m"), ("quarterly", "q")):
        snap = read_snapshot(engine, group)
        period_key = f"csc_{group}_period"
        date_key = f"csc_{group}_announce_date"
        slot_values[period_key] = snap["period_label"] or "—"
        slot_values[date_key] = snap["announce_date"] or "—"
        confidence[period_key] = "high" if snap["period_label"] else "low"
        confidence[date_key] = "high" if snap["announce_date"] else "low"
        for row in snap["rows"]:
            idx = row["slot_index"]
            prev = row["prev_price"]
            change = row["change_amount"]
            new = row["new_price"]
            # Empty/zero rows → render as "—" so users see they need filling
            empty = (prev == 0 and change == 0)
            for col_key, val in (
                (f"csc_{prefix}_{idx:02d}_prev",   prev),
                (f"csc_{prefix}_{idx:02d}_change", change),
                (f"csc_{prefix}_{idx:02d}_new",    new),
            ):
                if empty:
                    slot_values[col_key] = "—"
                    confidence[col_key] = "low"
                else:
                    if col_key.endswith("_change"):
                        slot_values[col_key] = f"+{val}" if val >= 0 else str(val)
                    else:
                        slot_values[col_key] = f"{val:,}"
                    confidence[col_key] = "high"


def _fill_history_slots(
    slot_values: dict[str, str],
    confidence: dict[str, str],
    store: "SqliteHistoryStore",
    meeting_d: date,
) -> None:
    """Populate hist_d_h0..h6, hist_<topic>_h0..h6, hist_<topic>_v_h0..h6.

    h0 = current week (rightmost column). h6 = oldest (leftmost).
    Empty cells render as "—" with low confidence.
    """
    # We fetch 8 records (one extra) so the leftmost-displayed column's
    # week-over-week delta can still be computed against its prior week.
    # Display indices 1..7; the prior-week reference for column 0 is index 0.
    DISPLAY = 7
    LOOKBACK = DISPLAY + 1

    # ── shared date headers from the densest topic ──
    raw_seed: list[tuple[date, float | None]] = []
    for _, src_key, _ in HISTORY_TOPICS:
        raw_seed = store.list_recent(src_key, meeting_d, count=LOOKBACK)
        if raw_seed:
            break
    while len(raw_seed) < LOOKBACK:
        raw_seed.insert(0, (None, None))  # type: ignore[arg-type]
    # display_seed = the rightmost 7
    display_seed = raw_seed[-DISPLAY:]

    for i in range(DISPLAY):
        h_idx = (DISPLAY - 1) - i  # i=0 → h6 (oldest displayed), i=6 → h0 (newest)
        d, _ = display_seed[i]
        slot_key = f"hist_d_h{h_idx}"
        if d is None:
            slot_values[slot_key] = "—"
            confidence[slot_key] = "low"
        else:
            slot_values[slot_key] = f"{d.month}/{d.day}"
            confidence[slot_key] = "high"

    # ── per-topic price + delta ──
    for topic_key, src_key, _ in HISTORY_TOPICS:
        pairs = store.list_recent(src_key, meeting_d, count=LOOKBACK)
        while len(pairs) < LOOKBACK:
            pairs.insert(0, (None, None))  # type: ignore[arg-type]
        display = pairs[-DISPLAY:]
        prior_for_first = pairs[-DISPLAY - 1]
        for i in range(DISPLAY):
            h_idx = (DISPLAY - 1) - i
            d_at_col, val = display[i]
            price_key = f"hist_{topic_key}_h{h_idx}"
            delta_key = f"hist_{topic_key}_v_h{h_idx}"
            if val is None:
                # Distinguish "no row at all" from "row with explicit
                # 未開盤 value" — the latter has a date.
                slot_values[price_key] = "未開盤" if d_at_col is not None else "—"
                slot_values[delta_key] = "—"  # no number → no delta
                confidence[price_key] = "high" if d_at_col is not None else "low"
                confidence[delta_key] = "low"
            else:
                slot_values[price_key] = f"{int(val):,}"
                confidence[price_key] = "high"
                # Walk left until we find a non-None prev value (skipping
                # consecutive 未開盤 weeks).
                prev_val = None
                for j in range(i - 1, -2, -1):
                    if j < 0:
                        prev_val = prior_for_first[1]
                        break
                    if display[j][1] is not None:
                        prev_val = display[j][1]
                        break
                if prev_val is None:
                    slot_values[delta_key] = "—"
                    confidence[delta_key] = "low"
                else:
                    diff = int(val - prev_val)
                    slot_values[delta_key] = f"+{diff}" if diff >= 0 else str(diff)
                    confidence[delta_key] = "high"


def _node_render(state: GenerationState) -> dict:
    """Render the Word document using DocxRenderer."""
    cfg = get_settings()
    run_id = state["run_id"]
    meeting_d = state["meeting_date"]
    user = state.get("started_by", "system")

    out_filename = (
        f"會議記錄_{meeting_d.isoformat()}_{user}_"
        f"{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.docx"
    )
    out_path = cfg.OUTPUT_DIR / out_filename
    renderer = DocxRenderer(cfg.TEMPLATE_PATH)
    renderer.render(
        slot_values=state.get("slot_values", {}),
        output_path=out_path,
        confidence=state.get("confidence", {}),
    )
    return {"output_path": str(out_path)}


def build_graph():
    """Compile the LangGraph workflow.

    fetch → validate → persist → narrate → render
                            ↑
                  history nodes can read from price_history
                  to fill 七.近期盤價 slots in narrate.
    """
    graph = StateGraph(GenerationState)
    graph.add_node("fetch", _node_fetch)
    graph.add_node("validate", _node_validate)
    graph.add_node("persist", _node_persist)
    graph.add_node("narrate", _node_narrate)
    graph.add_node("render", _node_render)

    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "validate")
    graph.add_edge("validate", "persist")
    graph.add_edge("persist", "narrate")
    graph.add_edge("narrate", "render")
    graph.add_edge("render", END)

    return graph.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
