"""Optional server-side audit logging for OE Testing runs (user inputs, AI inputs/outputs, errors).

One JSON-lines file is written per run. AI-call sites emit events through ``audit_event``,
which is a no-op unless a run has been started with ``audit_run`` on the current thread/context,
so other modules (playgrounds, anonymisation, redaction) are never logged.
"""
import json
import threading
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

_settings_lock = threading.Lock()
_current: ContextVar["AuditLog | None"] = ContextVar("oe_audit_log", default=None)


def is_audit_enabled(settings_file: str) -> bool:
    with _settings_lock:
        try:
            return bool(json.loads(Path(settings_file).read_text(encoding="utf-8")).get("audit_logging_enabled"))
        except (OSError, json.JSONDecodeError):
            return False


def set_audit_enabled(settings_file: str, enabled: bool) -> None:
    path = Path(settings_file)
    with _settings_lock:
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            settings = {}
        settings["audit_logging_enabled"] = enabled
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


class AuditLog:
    def __init__(self, path: Path):
        self.path = path

    def event(self, event_type: str, **data: Any) -> None:
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event_type, **data}
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
        except OSError:
            pass  # Auditing must never break the test run itself.


def audit_event(event_type: str, **data: Any) -> None:
    log = _current.get()
    if log is not None:
        log.event(event_type, **data)


@contextmanager
def audit_run(enabled: bool, log_dir: str, job_id: str, inputs: dict[str, Any]) -> Iterator[None]:
    """Records the start, inputs, outcome and any exception of one OE test run when enabled."""
    if not enabled:
        yield
        return

    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log = AuditLog(directory / f"oe_test_{stamp}_{job_id}.log")
    token = _current.set(log)
    log.event("run_started", job_id=job_id, user_inputs=inputs)
    try:
        yield
    except Exception as exc:
        log.event("run_failed", error=str(exc), exception_type=type(exc).__name__, traceback=traceback.format_exc())
        raise
    else:
        log.event("run_completed")
    finally:
        _current.reset(token)
