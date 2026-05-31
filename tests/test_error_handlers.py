"""
Unit tests for Campus Guide Kiosk
"""

import pytest
import json
import numpy as np
from unittest.mock import patch, MagicMock, Mock
from error_handlers import (
    sanitize_input,
    validate_query,
    ValidationError,
    validate_api_request,
    create_success_response,
    create_error_response,
)


class TestInputValidation:
    """Test input validation and sanitization."""

    def test_sanitize_input_valid(self):
        """Test sanitizing valid input."""
        result = sanitize_input("Where is the Registrar?")
        assert result == "Where is the Registrar?"

    def test_sanitize_input_with_whitespace(self):
        """Test sanitizing input with extra whitespace."""
        result = sanitize_input("  Where is the Registrar?  ")
        assert result == "Where is the Registrar?"

    def test_sanitize_input_empty(self):
        """Test sanitizing empty input."""
        with pytest.raises(ValidationError) as exc_info:
            sanitize_input("")
        assert "non-empty string" in str(exc_info.value)

    def test_sanitize_input_too_long(self):
        """Test sanitizing input that exceeds max length."""
        long_query = "a" * 501
        with pytest.raises(ValidationError) as exc_info:
            sanitize_input(long_query, max_length=500)
        assert "too long" in str(exc_info.value)

    def test_sanitize_input_sql_injection(self):
        """Test sanitizing SQL injection attempts."""
        with pytest.raises(ValidationError) as exc_info:
            sanitize_input("'; DROP TABLE faqs; --")
        assert "Invalid characters" in str(exc_info.value)

    def test_sanitize_input_script_tag(self):
        """Test sanitizing script tag injection."""
        with pytest.raises(ValidationError) as exc_info:
            sanitize_input("<script>alert('xss')</script>")
        assert "Invalid characters" in str(exc_info.value)

    def test_sanitize_input_event_handler(self):
        """Test sanitizing event handler injection."""
        with pytest.raises(ValidationError) as exc_info:
            sanitize_input("<img onerror=alert('xss')>")
        assert "Invalid characters" in str(exc_info.value)

    def test_validate_query(self):
        """Test query validation."""
        result = validate_query("  How do I enroll?  ")
        assert result == "How do I enroll?"

    def test_validate_query_invalid(self):
        """Test query validation with invalid input."""
        with pytest.raises(ValidationError):
            validate_query("'; DROP TABLE;")


class TestAPIValidation:
    """Test API request validation."""

    def test_validate_api_request_valid(self):
        """Test validating valid API request."""
        data = {"query": "Where is the library?", "extra": "field"}
        result = validate_api_request(data, ["query"])
        assert result == data

    def test_validate_api_request_missing_field(self):
        """Test validating API request with missing required field."""
        data = {"other_field": "value"}
        with pytest.raises(ValidationError) as exc_info:
            validate_api_request(data, ["query"])
        assert "Missing required field: query" in str(exc_info.value)

    def test_validate_api_request_empty_data(self):
        """Test validating empty API request."""
        with pytest.raises(ValidationError) as exc_info:
            validate_api_request({}, ["query"])
        assert "Request body cannot be empty" in str(exc_info.value)

    def test_validate_api_request_none_data(self):
        """Test validating None API request."""
        with pytest.raises(ValidationError) as exc_info:
            validate_api_request(None, ["query"])
        assert "cannot be empty" in str(exc_info.value)

    def test_validate_api_request_multiple_fields(self):
        """Test validating request with multiple required fields."""
        data = {"query": "test", "category": "general"}
        result = validate_api_request(data, ["query", "category"])
        assert result == data

    def test_validate_api_request_missing_one_of_many(self):
        """Test validating request missing one of multiple required fields."""
        data = {"query": "test"}
        with pytest.raises(ValidationError) as exc_info:
            validate_api_request(data, ["query", "category"])
        assert "Missing required field: category" in str(exc_info.value)


class TestResponseFormatting:
    """Test response formatting functions."""

    def test_create_success_response(self):
        """Test creating success response."""
        data = {"result": "test"}
        response = create_success_response(data, "Test message")
        assert response["status"] == "success"
        assert response["message"] == "Test message"
        assert response["data"] == data

    def test_create_error_response(self):
        """Test creating error response."""
        response, status = create_error_response("TestError", "Test error message", 400)
        assert response["status"] == "error"
        assert response["error"] == "TestError"
        assert response["message"] == "Test error message"
        assert status == 400

    def test_create_error_response_default_status(self):
        """Test creating error response with default status code."""
        response, status = create_error_response("TestError", "Test error")
        assert status == 400


class TestErrorExceptions:
    """Test custom error exceptions."""

    def test_validation_error(self):
        """Test ValidationError."""
        error = ValidationError("Test message")
        assert error.error_type == "ValidationError"
        assert error.status_code == 400
        assert str(error) == "Test message"

    def test_validation_error_is_api_error(self):
        """Test ValidationError inherits from APIError."""
        from error_handlers import APIError

        error = ValidationError("Test")
        assert isinstance(error, APIError)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
