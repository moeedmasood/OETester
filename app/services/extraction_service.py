"""Calls the UnifiedAPI Extraction service for a single sample file."""
import logging
from pathlib import Path
from typing import Any

from ai_unified_api_client.document_insights.models import ExtractionResponse, ExtractionSchema
from ai_unified_api_client.errors import APIError
from ai_unified_api_client.unified_api import UnifiedAPI

from .error_handling import NOT_EXTRACTED_NOTICE, friendly_api_error
from .schema_builder import build_pydantic_model

logger = logging.getLogger(__name__)


def flag_missing_fields(extracted: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Replaces None-valued fields with a not-extracted notice, returning their names."""
    missing_fields = [name for name, value in extracted.items() if value is None]
    for name in missing_fields:
        extracted[name] = NOT_EXTRACTED_NOTICE
    return extracted, missing_fields


def extract_sample(
        api: UnifiedAPI, file_path: Path, extraction_fields: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """Extract structured data from one sample file according to extraction_fields.

    Returns a tuple of (extraction_result, missing_field_names). Fields the model
    could not find (returned as None) are replaced with a user-facing notice rather
    than being silently passed on as None.
    """
    model = build_pydantic_model("ExtractionFields", extraction_fields)
    schema = ExtractionSchema.from_pydantic(model)
    service = api.extractor
    job_id = None
    try:
        # Submit without waiting so we retain the job_id, letting us delete the
        # job (and its generated files) from the AI service once we're done with it.
        submitted = service.execute(
            extraction_schema=schema, document=file_path, model_id="amazon.nova-pro-v1:0",
            system_prompt="You are an AI system responsible for extracting structured data from documents / images.",
            prompt="Please extract the relevant fields from the provided document according to the specified schema.",
            wait=False,
        )
        job_id = submitted.job_id
        download_uri = f"{api.client.base_url}{service.JOB_PATH.format(job_id=job_id)}"
        result = api.client.wait_for_job_completion(job_id=job_id, download_url=download_uri)
        response = ExtractionResponse.from_dict(result)
    except APIError as exc:
        raise friendly_api_error(exc, f"Extraction of '{file_path.name}'") from exc
    finally:
        if job_id:
            try:
                service.delete(job_id)
            except Exception:
                logger.warning("Failed to delete extraction job %s", job_id, exc_info=True)

    extracted = response.extraction_result or {}
    return flag_missing_fields(extracted)

