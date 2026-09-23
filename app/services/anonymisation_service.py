"""Calls the UnifiedAPI Anonymisation (PII redaction) service for a batch of files."""
import logging
from pathlib import Path
from typing import Any

from ai_unified_api_client.errors import APIError
from ai_unified_api_client.guardrails.models import AnonymisationResponse
from ai_unified_api_client.models import Document
from ai_unified_api_client.unified_api import UnifiedAPI

from .error_handling import friendly_api_error
from .job_manager import Job

logger = logging.getLogger(__name__)

ENTITY_TYPES = [
    "EMAIL_ADDRESS", "PHONE_NUMBER", "TFN", "DRIVER_LICENSE",
    "LOCATION", "PERSON", "ABN", "MEDICARE",
]


def anonymise_files(
        job: Job, api: UnifiedAPI, file_paths: list[Path], entity_types: list[str]
) -> list[dict[str, Any]]:
    """Anonymises each file in turn, returning one result dict per file.

    Each result has: filename, ok, download_url, redacted_entity_count, error.
    """
    service = api.anonymisation
    results: list[dict[str, Any]] = []
    for file_path in file_paths:
        job.log(f"Anonymising {file_path.name}...")
        job_id = None
        try:
            submitted = service.execute(
                document=Document.from_file(file_path), entity_types=entity_types, wait=False,
            )
            job_id = submitted.job_id
            download_uri = f"{api.client.base_url}{service.JOB_PATH.format(job_id=job_id)}"
            raw_result = api.client.wait_for_job_completion(job_id=job_id, download_url=download_uri)
            response = AnonymisationResponse.from_dict(raw_result)
            entities = response.redacted_entities or []
            results.append({
                "filename": file_path.name,
                "ok": True,
                "download_url": response.download_url,
                "redacted_entity_count": len(entities),
                "error": None,
            })
            job.log(f"Anonymised {file_path.name} - {len(entities)} entities redacted.")
        except APIError as exc:
            err = friendly_api_error(exc, f"Anonymisation of '{file_path.name}'")
            job.log(f"Failed: {err}")
            results.append({
                "filename": file_path.name, "ok": False, "download_url": None,
                "redacted_entity_count": 0, "error": str(err),
            })
        except Exception as exc:  # noqa: BLE001 - surface any failure per-file, keep processing the rest
            job.log(f"Failed to anonymise {file_path.name}: {exc}")
            results.append({
                "filename": file_path.name, "ok": False, "download_url": None,
                "redacted_entity_count": 0, "error": str(exc),
            })
        finally:
            if job_id:
                try:
                    service.delete(job_id)
                except Exception:
                    logger.warning("Failed to delete anonymisation job %s", job_id, exc_info=True)
    job.log("Done.")
    return results
