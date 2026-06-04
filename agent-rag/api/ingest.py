from __future__ import annotations

import json
import os
import threading
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile

from api.schemas import IngestJobResponse

router = APIRouter(prefix="/admin", tags=["admin-ingest"])

_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def _set_job(job_id: str, **fields: Any) -> None:
    with _JOBS_LOCK:
        job = _JOBS.setdefault(job_id, {})
        job.update(fields)


def _run_ingest_job(job_id: str, file_path: str) -> None:
    _set_job(job_id, status="running", message="ingest started")
    try:
        _set_job(job_id, status="completed", message=f"ingest queued for {file_path}")
    except Exception as exc:
        _set_job(job_id, status="failed", message=str(exc))


@router.post("/ingest", response_model=IngestJobResponse)
async def ingest_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile | None = None,
) -> IngestJobResponse:
    job_id = str(uuid.uuid4())
    upload_dir = os.environ.get("INGEST_UPLOAD_DIR", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    if file is None:
        raise HTTPException(status_code=400, detail="file is required")

    dest = os.path.join(upload_dir, f"{job_id}_{file.filename}")
    content = await file.read()
    with open(dest, "wb") as handle:
        handle.write(content)

    _set_job(job_id, status="pending", message="queued", detail={"path": dest})
    background_tasks.add_task(_run_ingest_job, job_id, dest)
    return IngestJobResponse(job_id=job_id, status="pending", message="ingest job queued")


@router.get("/ingest/{job_id}", response_model=IngestJobResponse)
def ingest_status(job_id: str) -> IngestJobResponse:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return IngestJobResponse(
        job_id=job_id,
        status=job.get("status", "pending"),
        message=job.get("message", ""),
        detail=job.get("detail") or {},
    )
