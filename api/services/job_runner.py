"""Kolejka zadan w tle — logi, postep, jedno zadanie naraz."""

from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from src.portal.job_context import bind_callbacks, capture_stdout_to_log, clear_callbacks

from api.predictor import predictor
from src.portal.operations import JOB_HANDLERS


@dataclass
class JobRecord:
    id: str
    job_type: str
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    log_lines: list[str] | None = None
    progress: int = 0
    progress_message: str = ""


class JobRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._running_id: str | None = None

    def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            items = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[
                :limit
            ]
            return [asdict(j) for j in items]

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def is_busy(self) -> bool:
        with self._lock:
            return self._running_id is not None

    def submit(self, job_type: str, **kwargs: Any) -> JobRecord:
        if job_type not in JOB_HANDLERS:
            raise ValueError(f"Nieznany typ zadania: {job_type}")

        with self._lock:
            if self._running_id is not None:
                raise RuntimeError("Inne zadanie jest juz w toku — poczekaj na zakonczenie.")
            job_id = uuid.uuid4().hex[:12]
            record = JobRecord(
                id=job_id,
                job_type=job_type,
                status="queued",
                created_at=datetime.now(timezone.utc).isoformat(),
                log_lines=[],
            )
            self._jobs[job_id] = record
            self._running_id = job_id

        thread = threading.Thread(
            target=self._run,
            args=(job_id, job_type, kwargs),
            daemon=True,
        )
        thread.start()
        return record

    def _append_log(self, record: JobRecord, line: str) -> None:
        if record.log_lines is None:
            record.log_lines = []
        record.log_lines.append(line)

    def _run(self, job_id: str, job_type: str, kwargs: dict[str, Any]) -> None:
        with self._lock:
            record = self._jobs[job_id]
            record.status = "running"
            record.started_at = datetime.now(timezone.utc).isoformat()

        def on_log(line: str) -> None:
            with self._lock:
                self._append_log(record, line)

        def on_progress(pct: int, message: str) -> None:
            with self._lock:
                record.progress = pct
                if message:
                    record.progress_message = message

        bind_callbacks(on_log, on_progress)
        try:
            handler = JOB_HANDLERS[job_type]
            with capture_stdout_to_log():
                result = handler(**kwargs)
            if (
                job_type.startswith("train")
                or job_type.startswith("dvc")
                or job_type == "check_drift_retrain"
            ):
                try:
                    predictor.load()
                except FileNotFoundError:
                    pass
            with self._lock:
                record.status = "success"
                record.result = result
                record.progress = 100
                record.progress_message = "Zakonczono"
        except Exception as exc:
            with self._lock:
                record.status = "failed"
                record.error = f"{exc}\n{traceback.format_exc()[-4000:]}"
                self._append_log(record, str(exc))
        finally:
            clear_callbacks()
            with self._lock:
                record.finished_at = datetime.now(timezone.utc).isoformat()
                self._running_id = None


job_runner = JobRunner()
