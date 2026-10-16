"""
Error handling, validation, and security utilities.
"""

import hmac
import re
from typing import Any, Tuple
from logging_config import log_error


class APIError(Exception):
    """Base exception for API errors."""

    def __init__(
        self, message: str, status_code: int = 400, error_type: str = "ValidationError"
    ):
        self.message = message
        self.status_code = status_code
        self.error_type = error_type
        super().__init__(self.message)


class ValidationError(APIError):
    """Raised when input validation fails."""

    def __init__(self, message: str):
        super().__init__(message, 400, "ValidationError")


class NotFoundError(APIError):
    """Raised when resource is not found."""

    def __init__(self, message: str):
        super().__init__(message, 404, "NotFoundError")


class InternalServerError(APIError):
    """Raised for internal server errors."""

    def __init__(self, message: str = "Internal server error"):
        super().__init__(message, 500, "InternalServerError")


def sanitize_input(text: str, max_length: int = 500) -> str:
    """
    Sanitize user input by removing dangerous characters and limiting length.

    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized text

    Raises:
        ValidationError: If input is invalid
    """
    if not text or not isinstance(text, str):
        raise ValidationError("Query must be a non-empty string")

    # Strip whitespace
    text = text.strip()

    # Check length
    if len(text) > max_length:
        raise ValidationError(
            f"Query too long. Maximum {max_length} characters allowed."
        )

    if len(text) < 1:
        raise ValidationError("Query cannot be empty")

    # Remove potentially harmful patterns (SQL injection, script tags, etc.)
    dangerous_patterns = [
        r"<script[^>]*>.*?</script>",  # Script tags
        r"javascript:",  # JavaScript protocol
        r"on\w+\s*=",  # Event handlers (onload, onclick, etc.)
        r"--",  # SQL comments
        r";.*DROP",  # SQL DROP commands
        r";.*DELETE",  # SQL DELETE commands
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            raise ValidationError("Invalid characters detected in query")

    return text


def validate_api_request(data: dict, required_fields: list) -> dict:
    """
    Validate API request data.

    Args:
        data: Request JSON data
        required_fields: List of required field names

    Returns:
        Validated data dictionary

    Raises:
        ValidationError: If validation fails
    """
    if not data:
        raise ValidationError("Request body cannot be empty")

    for field in required_fields:
        if field not in data or not data[field]:
            raise ValidationError(f"Missing required field: {field}")

    return data


def error_response(error: Exception) -> Tuple[dict, int]:
    """
    Convert exception to API error response.

    Args:
        error: Exception instance

    Returns:
        Tuple of (response_dict, status_code)
    """
    if isinstance(error, APIError):
        log_error(error.error_type, error.message)
        return {
            "error": error.error_type,
            "message": error.message,
            "status": "error",
        }, error.status_code

    # Generic server error
    error_msg = str(error)
    log_error("UnexpectedError", error_msg, str(type(error)))
    return {
        "error": "InternalServerError",
        "message": "An unexpected error occurred. Please try again later.",
        "status": "error",
    }, 500


def validate_query(query: Any, max_length: int = 500) -> str:
    """Validate and sanitize user query."""
    # sanitize_input() already rejects non-str/empty input (and strips it),
    # so there's no need to duplicate that isinstance check here.
    return sanitize_input(query, max_length)


def check_admin_secret(provided: str, expected: str) -> bool:
    """
    Constant-time comparison for admin secrets (X-Reload-Secret / ?secret=).
    Returns True if access should be allowed:
      - if no secret is configured (expected is empty), access is allowed
        (dev convenience — callers should log a warning at startup instead)
      - otherwise the provided secret must match exactly, compared in
        constant time to avoid leaking the secret via response timing.
    """
    if not expected:
        return True
    return hmac.compare_digest(provided or "", expected)


def create_success_response(data: Any = None, message: str = "Success") -> dict:
    """Create standardized success response."""
    return {"status": "success", "message": message, "data": data}


def create_error_response(
    error_type: str, message: str, status_code: int = 400
) -> Tuple[dict, int]:
    """Create standardized error response."""
    return {"status": "error", "error": error_type, "message": message}, status_code
