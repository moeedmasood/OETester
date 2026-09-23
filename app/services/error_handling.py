"""Shared helpers for turning UnifiedAPI errors into user-facing messages."""
from ai_unified_api_client.errors import APIError

SUPPORT_CONTACT = "giausecaseinfo@insigniafinancial.com.au"

NOT_EXTRACTED_NOTICE = (
    "Not extracted - this field could not be found in the document and will not be "
    f"processed further. For further questions contact {SUPPORT_CONTACT}."
)

_STATUS_REASONS = {
    400: "The request was rejected as invalid or unsafe (e.g. blocked by a content safety check).",
    401: "The application's credentials for the AI service were rejected.",
    403: "The request was blocked by the AI service (e.g. a content safety/prompt-attack guardrail).",
    429: "The AI service is rate-limiting requests right now. Please try again shortly.",
}


def friendly_api_error(exc: APIError, action: str) -> RuntimeError:
    """Wraps an APIError into a RuntimeError with a clear, user-facing message."""
    reason = _STATUS_REASONS.get(exc.status_code, "The AI service returned an error.")
    message = (
        f"{action} failed (HTTP {exc.status_code}): {reason} "
        f"For further assistance, contact {SUPPORT_CONTACT}."
    )
    return RuntimeError(message)
