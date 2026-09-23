"""In-memory job store for background OE-testing runs, polled by the browser."""
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_jobs_lock = threading.Lock()
_jobs: dict[str, "Job"] = {}


@dataclass
class Job:
    id: str
    status: str = "pending"  # pending | running | done | error
    steps: list[str] = field(default_factory=list)
    error: str | None = None
    output_filename: str | None = None
    result: Any = None  # generic payload for jobs that don't produce a single output file

    def log(self, message: str) -> None:
        with _jobs_lock:
            self.steps.append(message)

    def to_dict(self) -> dict[str, Any]:
        with _jobs_lock:
            return {
                "id": self.id,
                "status": self.status,
                "steps": list(self.steps),
                "error": self.error,
                "output_filename": self.output_filename,
                "result": self.result,
            }


def create_job() -> Job:
    job = Job(id=str(uuid.uuid4()))
    with _jobs_lock:
        _jobs[job.id] = job
    return job


def get_job(job_id: str) -> Job | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def run_in_background(job: Job, target: Callable[[Job], Path | None]) -> None:
    """Runs target(job) on a background thread, updating job status/steps as it goes.

    ``target`` may return a Path to a single output file (sets ``output_filename``),
    or ``None`` for jobs that report their results via ``job.result`` instead.
    """

    def _runner():
        job.status = "running"
        try:
            output_path = target(job)
            if output_path is not None:
                job.output_filename = output_path.name
            job.status = "done"
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            job.error = str(exc)
            job.log(f"ERROR: {exc}")
            job.log(traceback.format_exc())
            job.status = "error"

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
