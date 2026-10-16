"""
API route tests for Campus Guide Kiosk
"""

import json
from unittest.mock import patch

import pytest

# Mock Firebase and the embedding model before importing app


@pytest.fixture(autouse=True)
def mock_dependencies():
    """Mock external dependencies."""
    with patch("firebase_admin.initialize_app"):
        with patch("firebase_admin._apps", []):
            with patch("firebase_admin.credentials.Certificate"):
                with patch("firebase_admin.firestore.client"):
                    with patch("sentence_transformers.SentenceTransformer"):
                        yield


@pytest.fixture
def app():
    """Create Flask test app."""
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check_success(self, client):
        """Test health check returns OK status."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "data" in data

    def test_health_check_contains_system_info(self, client):
        """Test health check contains system information."""
        response = client.get("/api/v1/health")
        data = json.loads(response.data)
        assert "faq_count" in data["data"]
        assert "model_loaded" in data["data"]
        assert "firebase_status" in data["data"]


class TestAskEndpoint:
    """Test /api/v1/ask endpoint."""

    def test_ask_empty_body(self, client):
        """Test ask endpoint with empty body."""
        response = client.post(
            "/api/v1/ask", data="{}", content_type="application/json"
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["status"] == "error"

    def test_ask_missing_query(self, client):
        """Test ask endpoint with missing query field."""
        response = client.post(
            "/api/v1/ask",
            data=json.dumps({"other": "field"}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_ask_invalid_json(self, client):
        """Test ask endpoint with invalid JSON."""
        response = client.post(
            "/api/v1/ask", data="invalid json", content_type="application/json"
        )
        assert response.status_code in [400, 415]

    def test_ask_non_string_query(self, client):
        """A non-string 'query' value must be a clean 400, not a 500 (regression)."""
        response = client.post(
            "/api/v1/ask",
            data=json.dumps({"query": 12345}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["status"] == "error"


class TestReloadEndpoint:
    """Test /api/v1/reload endpoint."""

    def test_reload_success(self, client):
        """Test reload endpoint without secret requirement."""
        response = client.post("/api/v1/reload")
        # Should either succeed or require secret
        assert response.status_code in [200, 401]

    def test_reload_with_wrong_secret(self, client):
        """Test reload endpoint with wrong secret."""
        # If secret is required, wrong secret should fail
        response = client.post(
            "/api/v1/reload", headers={"X-Reload-Secret": "wrong-secret"}
        )
        # May require correct secret or may not have one configured
        assert response.status_code in [200, 401]


class TestIndexRoute:
    """Test index route."""

    def test_index_returns_html(self, client):
        """Test index route returns HTML."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"<!DOCTYPE html>" in response.data or b"<html" in response.data


class TestErrorHandling:
    """Test error handling."""

    def test_404_error(self, client):
        """Test 404 error handling."""
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404
        data = json.loads(response.data)
        assert data["status"] == "error"

    def test_method_not_allowed(self, client):
        """Test method not allowed."""
        response = client.get("/api/v1/ask")  # POST only
        assert response.status_code == 405


class TestSecurityHeaders:
    """Test security headers."""

    def test_security_headers_present(self, client):
        """Test that security headers are present."""
        response = client.get("/")
        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "X-Frame-Options" in response.headers
        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"


class TestCORS:
    """Test CORS is actually enforced on API routes (regression)."""

    def test_cors_headers_present_on_api_route(self, client):
        """Preflight-style request to an API route should carry CORS headers."""
        response = client.get(
            "/api/v1/health", headers={"Origin": "http://example.com"}
        )
        assert "Access-Control-Allow-Origin" in response.headers


class TestAnalyticsEndpoint:
    """Test /api/v1/analytics endpoint validation."""

    def test_analytics_invalid_limit(self, client):
        """A non-numeric 'limit' query param must be a clean 400, not a 500."""
        response = client.get("/api/v1/analytics?limit=notanumber")
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["status"] == "error"


FAQ_MATCH = [
    {
        "answer": "The Clinic is on the first floor of the Admin Office.",
        "category": "campus",
        "generated_questions": ["Where is the Clinic?"],
        "score": 0.92,
    }
]


class TestGeminiResilience:
    """Gemini outages must degrade gracefully and never be cached."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        import app as app_module

        app_module.cached_search_and_respond.cache_clear()
        yield
        app_module.cached_search_and_respond.cache_clear()

    def test_quota_errors_are_detected_for_rotation(self):
        import app as app_module

        class FakeApiError(Exception):
            code = 429

        assert app_module._is_quota_error(FakeApiError("quota"))
        assert app_module._is_quota_error(RuntimeError("429 RESOURCE_EXHAUSTED"))
        assert not app_module._is_quota_error(ValueError("bad request"))

    def test_ask_falls_back_to_faq_answer_when_gemini_is_down(self, client):
        import app as app_module

        down = app_module.GeminiUnavailable("busy")
        with patch("app.search_faqs", return_value=FAQ_MATCH), patch(
            "app.get_gemini_response", side_effect=down
        ):
            response = client.post("/api/v1/ask", json={"query": "where is the clinic"})

        assert response.status_code == 200
        body = json.loads(response.data)["data"]
        assert body["response"] == FAQ_MATCH[0]["answer"]
        assert body["suggested_questions"] == ["Where is the Clinic?"]

    def test_gemini_failure_is_not_cached(self, client):
        import app as app_module

        down = app_module.GeminiUnavailable("busy")
        with patch("app.search_faqs", return_value=FAQ_MATCH):
            with patch("app.get_gemini_response", side_effect=down):
                client.post("/api/v1/ask", json={"query": "where is the clinic"})
            with patch("app.get_gemini_response", return_value="Fresh AI answer."):
                response = client.post(
                    "/api/v1/ask", json={"query": "where is the clinic"}
                )

        assert json.loads(response.data)["data"]["response"] == "Fresh AI answer."


class TestAdminGate:
    """/reload and /analytics must fail closed in production without a secret."""

    def test_reload_rejected_in_production_without_secret(self, client, monkeypatch):
        import app as app_module

        monkeypatch.delenv("RELOAD_SECRET", raising=False)
        monkeypatch.setattr(app_module.config, "environment", "production")
        response = client.post("/api/v1/reload")
        assert response.status_code == 401

    def test_reload_requires_matching_secret_when_configured(self, client, monkeypatch):
        monkeypatch.setenv("RELOAD_SECRET", "s3cret")
        wrong = client.post("/api/v1/reload", headers={"X-Reload-Secret": "nope"})
        right = client.post("/api/v1/reload", headers={"X-Reload-Secret": "s3cret"})
        assert wrong.status_code == 401
        assert right.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
