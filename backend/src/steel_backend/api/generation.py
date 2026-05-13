"""Generation endpoints — start run, poll status, update internal data, download.

Architecture:
  Render free-tier proxies cut HTTP requests around 100 s. The LangGraph
  workflow regularly runs 90-180 s. So /run and /internal-data MUST NOT
  block — they create the run row, launch the graph as a background
  asyncio task, and return immediately with status="running". The
  frontend polls /{run_id} every couple of seconds until status flips.

  The background task writes the final state (slot_values, confidence,
  serialised fetched_index, output_path) into `GenerationRun.result_json`
  on success, then sets status accordingly. The /{run_id} endpoint
  reads from there — no graph re-invocation.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date as date_t
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.rate_limit import limiter
from ..config import get_settings
from ..core.dates import opening_monday
from ..core.orchestrator import get_graph
from ..core.slot_schema import SLOTS
from ..sources.base import FetchResult
from ..storage.models import GenerationRun
from ..storage.sqlite_store import get_engine
from .schemas import (
    GenerationStartRequest,
    GenerationStatusResponse,
    InternalDataRequest,
    SlotValueDto,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# Holds references to in-flight background tasks so asyncio doesn't GC them
# mid-flight (asyncio.create_task only retains a weak reference). Cleaned up
# in the task's finally block.
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


# ──────────────────────────────────────────────────────────────
# Response serialisation
# ──────────────────────────────────────────────────────────────

def _format_state_to_response(
    *,
    run_id: int,
    status_str: str,
    meeting_date: date_t,
    slot_values: dict[str, str],
    confidence: dict[str, str],
    fetched_index: dict[str, Any] | None = None,
    output_path: str | None = None,
) -> GenerationStatusResponse:
    fetched_index = fetched_index or {}
    slots: list[SlotValueDto] = []
    for s in SLOTS:
        rendered = slot_values.get(s.key)
        fetched = fetched_index.get(s.key)
        # fetched may be either a FetchResult instance (in-process) or a
        # plain dict (deserialised from result_json). Handle both.
        if fetched is None:
            raw_value, source_url = None, None
        elif isinstance(fetched, dict):
            raw_value = fetched.get("value")
            source_url = fetched.get("source_url")
        else:
            raw_value = getattr(fetched, "value", None)
            source_url = getattr(fetched, "source_url", None)
        slots.append(
            SlotValueDto(
                slot_key=s.key,
                label=s.label,
                value=rendered,
                raw_value=raw_value,
                unit=s.unit,
                confidence=confidence.get(s.key, "high"),
                source=s.source,
                source_url=source_url,
            )
        )
    return GenerationStatusResponse(
        run_id=run_id,
        status=status_str,
        meeting_date=meeting_date,
        slots=slots,
        has_output=bool(output_path) and Path(output_path).exists(),
    )


def _serialise_state(final_state: dict[str, Any]) -> str:
    """Pack the final graph state into a JSON string for DB storage."""
    fetched_list: list[dict[str, Any]] = []
    for r in final_state.get("validated", []):
        if isinstance(r, FetchResult):
            fetched_list.append(r.model_dump())
        elif isinstance(r, dict):
            fetched_list.append(r)
    payload = {
        "slot_values": final_state.get("slot_values", {}),
        "confidence": final_state.get("confidence", {}),
        "fetched": fetched_list,
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _deserialise_state(
    blob: str,
) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, Any]]]:
    if not blob:
        return {}, {}, {}
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError:
        return {}, {}, {}
    slot_values = payload.get("slot_values") or {}
    confidence = payload.get("confidence") or {}
    fetched_index: dict[str, dict[str, Any]] = {}
    for item in payload.get("fetched") or []:
        key = item.get("slot_key")
        if key:
            fetched_index[key] = item
    return slot_values, confidence, fetched_index


# ──────────────────────────────────────────────────────────────
# Background worker
# ──────────────────────────────────────────────────────────────

async def _execute_graph_and_persist(
    *,
    run_id: int,
    meeting_date: date_t,
    fengxing_d: date_t,
    started_by: str,
    internal_data: dict[str, str],
    extra_state: dict[str, Any] | None = None,
) -> None:
    """Run the LangGraph workflow, then persist result to GenerationRun.

    This runs **detached** from the HTTP request — exceptions are caught and
    written to the run row's `notes` column. The HTTP client polls /{id}
    to learn the outcome.
    """
    engine = get_engine()
    try:
        graph = get_graph()
        initial_state: dict[str, Any] = {
            "run_id": run_id,
            "meeting_date": meeting_date,
            "fengxing_open_date": fengxing_d,
            "started_by": started_by,
            "internal_data": internal_data,
            "retry_count": 0,
            "max_retries": 3,
        }
        if extra_state:
            initial_state.update(extra_state)
        final_state = await graph.ainvoke(initial_state)
        output_path = final_state.get("output_path")
        issues = final_state.get("issues") or []
        new_status = "partial" if issues else "success"

        with Session(engine) as s:
            run = s.get(GenerationRun, run_id)
            if run is None:
                return
            run.status = new_status
            run.finished_at = datetime.utcnow()
            run.output_path = output_path
            run.result_json = _serialise_state(final_state)
            if issues:
                run.notes = "; ".join(str(i) for i in issues)[:500]
            s.add(run)
            s.commit()
    except Exception as exc:  # noqa: BLE001 — we want to capture *any* failure
        logger.exception("Generation run %s failed", run_id)
        with Session(engine) as s:
            run = s.get(GenerationRun, run_id)
            if run is not None:
                run.status = "failed"
                run.finished_at = datetime.utcnow()
                run.notes = f"{type(exc).__name__}: {exc}"[:500]
                s.add(run)
                s.commit()


def _spawn(task_coro: Any) -> None:
    task = asyncio.create_task(task_coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────

@router.post("/run", response_model=GenerationStatusResponse)
@limiter.limit(lambda: f"{get_settings().RATE_GENERATE_PER_HOUR}/hour")
async def start_run(
    request: Request,
    body: GenerationStartRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> GenerationStatusResponse:
    """Create a run row, launch the graph as a background task, return now.

    The frontend polls GET /{run_id} until status != 'running'.
    """
    engine = get_engine()
    with Session(engine) as s:
        run = GenerationRun(
            meeting_date=body.meeting_date,
            started_by=user.username,
            status="running",
        )
        s.add(run)
        s.commit()
        s.refresh(run)
        run_id = run.id
    assert run_id is not None

    fengxing_d = opening_monday(body.meeting_date)
    _spawn(
        _execute_graph_and_persist(
            run_id=run_id,
            meeting_date=body.meeting_date,
            fengxing_d=fengxing_d,
            started_by=user.username,
            internal_data={},
        )
    )

    return GenerationStatusResponse(
        run_id=run_id,
        status="running",
        meeting_date=body.meeting_date,
        slots=[],
        has_output=False,
    )


@router.post("/{run_id}/internal-data", response_model=GenerationStatusResponse)
async def update_internal_data(
    run_id: int,
    body: InternalDataRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> GenerationStatusResponse:
    """Re-render the Word doc after staff fills internal-data fields.

    Same async pattern as /run — flips status back to 'running', spawns
    the graph, returns immediately. Polling /{run_id} resumes.
    """
    engine = get_engine()
    with Session(engine) as s:
        run = s.get(GenerationRun, run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
        meeting_date = run.meeting_date
        run.status = "running"
        run.finished_at = None
        s.add(run)
        s.commit()

    internal = dict(body.data)
    if body.meeting_time is not None:
        internal["meeting_time"] = body.meeting_time

    fengxing_d = opening_monday(meeting_date)
    _spawn(
        _execute_graph_and_persist(
            run_id=run_id,
            meeting_date=meeting_date,
            fengxing_d=fengxing_d,
            started_by=user.username,
            internal_data=internal,
        )
    )

    return GenerationStatusResponse(
        run_id=run_id,
        status="running",
        meeting_date=meeting_date,
        slots=[],
        has_output=False,
    )


@router.get("/{run_id}", response_model=GenerationStatusResponse)
async def get_run(
    run_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> GenerationStatusResponse:
    """Status / result endpoint. While the background task is in flight
    we return status='running' with empty slots; once it completes the
    persisted `result_json` is deserialised back into the same shape the
    pre-background code used to return synchronously."""
    _ = user
    engine = get_engine()
    with Session(engine) as s:
        run = s.get(GenerationRun, run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
        run_status = run.status
        meeting_date = run.meeting_date
        output_path = run.output_path
        result_blob = run.result_json
        notes = run.notes

    if run_status == "running":
        return GenerationStatusResponse(
            run_id=run_id,
            status="running",
            meeting_date=meeting_date,
            slots=[],
            has_output=False,
        )

    if run_status == "failed":
        # Return 200 with status='failed' rather than an HTTP error so the
        # frontend's polling loop can distinguish "real generation failure"
        # from "cold-start 502". Frontend reads `notes` to populate the
        # toast.
        return GenerationStatusResponse(
            run_id=run_id,
            status="failed",
            meeting_date=meeting_date,
            slots=[],
            has_output=False,
            notes=notes or "Unknown error — check backend logs",
        )

    slot_values, confidence, fetched_index = _deserialise_state(result_blob)
    return _format_state_to_response(
        run_id=run_id,
        status_str=run_status,
        meeting_date=meeting_date,
        slot_values=slot_values,
        confidence=confidence,
        fetched_index=fetched_index,
        output_path=output_path,
    )


@router.get("/{run_id}/docx")
@limiter.limit(lambda: f"{get_settings().RATE_DOWNLOAD_PER_HOUR}/hour")
async def download_docx(
    request: Request,
    run_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> FileResponse:
    _ = user
    engine = get_engine()
    with Session(engine) as s:
        run = s.get(GenerationRun, run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
        if not run.output_path:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "No Word output for this run — has it finished?",
            )
        path = Path(run.output_path)
        if not path.exists():
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"Output file vanished: {path}"
            )
    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
