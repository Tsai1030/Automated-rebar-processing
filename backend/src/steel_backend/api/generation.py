"""Generation endpoints — start run, poll status, update internal data, download."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.rate_limit import limiter
from ..config import get_settings
from ..core.dates import opening_monday
from ..core.orchestrator import get_graph
from ..core.slot_schema import SLOTS, SLOTS_BY_KEY, SlotType
from ..storage.models import GenerationRun
from ..storage.sqlite_store import get_engine
from .schemas import (
    GenerationStartRequest,
    GenerationStatusResponse,
    InternalDataRequest,
    SlotValueDto,
)

router = APIRouter()


def _format_state_to_response(
    *,
    run_id: int,
    status_str: str,
    meeting_date,
    slot_values: dict[str, str],
    confidence: dict[str, str],
    fetched_index: dict[str, "any"] | None = None,
    output_path: str | None = None,
) -> GenerationStatusResponse:
    fetched_index = fetched_index or {}
    slots: list[SlotValueDto] = []
    for s in SLOTS:
        rendered = slot_values.get(s.key)
        fetched = fetched_index.get(s.key)
        slots.append(
            SlotValueDto(
                slot_key=s.key,
                label=s.label,
                value=rendered,
                raw_value=getattr(fetched, "value", None) if fetched else None,
                unit=s.unit,
                confidence=confidence.get(s.key, "high"),
                source=s.source,
                source_url=getattr(fetched, "source_url", None) if fetched else None,
            )
        )
    return GenerationStatusResponse(
        run_id=run_id,
        status=status_str,
        meeting_date=meeting_date,
        slots=slots,
        has_output=output_path is not None and Path(output_path).exists(),
    )


@router.post("/run", response_model=GenerationStatusResponse)
@limiter.limit(lambda: f"{get_settings().RATE_GENERATE_PER_HOUR}/hour")
async def start_run(
    request: Request,
    body: GenerationStartRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> GenerationStatusResponse:
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

    # Always derive 豐興 opening date as the Monday of the meeting week.
    # We deliberately ignore any client-supplied value to keep history clean.
    fengxing_d = opening_monday(body.meeting_date)

    graph = get_graph()
    initial_state = {
        "run_id": run_id,
        "meeting_date": body.meeting_date,
        "fengxing_open_date": fengxing_d,
        "started_by": user.username,
        "internal_data": {},
        "retry_count": 0,
        "max_retries": 3,
    }
    final_state = await graph.ainvoke(initial_state)
    output_path = final_state.get("output_path")

    with Session(engine) as s:
        run = s.get(GenerationRun, run_id)
        if run is not None:
            run.status = "success" if not final_state.get("issues") else "partial"
            run.finished_at = datetime.utcnow()
            run.output_path = output_path
            s.add(run)
            s.commit()

    fetched_index = {r.slot_key: r for r in final_state.get("validated", [])}
    return _format_state_to_response(
        run_id=run_id,
        status_str="success",
        meeting_date=body.meeting_date,
        slot_values=final_state.get("slot_values", {}),
        confidence=final_state.get("confidence", {}),
        fetched_index=fetched_index,
        output_path=output_path,
    )


@router.post("/{run_id}/internal-data", response_model=GenerationStatusResponse)
async def update_internal_data(
    run_id: int,
    body: InternalDataRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> GenerationStatusResponse:
    """Re-render the Word doc after staff fills internal-data fields."""
    engine = get_engine()
    with Session(engine) as s:
        run = s.get(GenerationRun, run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
        meeting_date = run.meeting_date

    internal = dict(body.data)
    if body.meeting_time is not None:
        internal["meeting_time"] = body.meeting_time

    fengxing_d = opening_monday(meeting_date)
    graph = get_graph()
    final_state = await graph.ainvoke({
        "run_id": run_id,
        "meeting_date": meeting_date,
        "fengxing_open_date": fengxing_d,
        "started_by": user.username,
        "internal_data": internal,
    })
    output_path = final_state.get("output_path")

    with Session(engine) as s:
        run = s.get(GenerationRun, run_id)
        if run is not None:
            run.output_path = output_path
            run.finished_at = datetime.utcnow()
            s.add(run)
            s.commit()

    fetched_index = {r.slot_key: r for r in final_state.get("validated", [])}
    return _format_state_to_response(
        run_id=run_id,
        status_str="success",
        meeting_date=meeting_date,
        slot_values=final_state.get("slot_values", {}),
        confidence=final_state.get("confidence", {}),
        fetched_index=fetched_index,
        output_path=output_path,
    )


@router.get("/{run_id}", response_model=GenerationStatusResponse)
async def get_run(
    run_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> GenerationStatusResponse:
    engine = get_engine()
    with Session(engine) as s:
        run = s.get(GenerationRun, run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
        return GenerationStatusResponse(
            run_id=run.id or 0,
            status=run.status,
            meeting_date=run.meeting_date,
            slots=[],
            has_output=bool(run.output_path) and Path(run.output_path).exists(),
        )


@router.get("/{run_id}/docx")
@limiter.limit(lambda: f"{get_settings().RATE_DOWNLOAD_PER_HOUR}/hour")
async def download_docx(
    request: Request,
    run_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> FileResponse:
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
