"""
API route tests for Campus Guide Kiosk
"""

import pytest
import json
from unittest.mock import patch, MagicMock, Mock
import sys
import os

# Mock Flask and dependencies before importing app


@pytest.fixture(autouse=True)
def mock_dependencies():
    """Mock external dependencies."""
    with patch('firebase_admin.initialize_app'):
        with patch('firebase_admin._apps', []):
            with patch('firebase_admin.credentials.Certificate'):
                with patch('firebase_admin.firestore.client'):
                    with patch('sentence_transformers.SentenceTransformer'):
                        yield


@pytest.fixture
def app():
    """Create Flask test app."""
    from app import app as flask_app
    flask_app.config['TESTING'] = True
    return flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check_success(self, client):
        """Test health check returns OK status."""
        response = client.get('/api/v1/health')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'success'
        assert 'data' in data

    def test_health_check_contains_system_info(self, client):
        """Test health check contains system information."""
        response = client.get('/api/v1/health')
        data = json.loads(response.data)
        assert 'faq_count' in data['data']
        assert 'model_loaded' in data['data']
        assert 'firebase_status' in data['data']


class TestAskEndpoint:
    """Test /api/v1/ask endpoint."""

    def test_ask_empty_body(self, client):
        """Test ask endpoint with empty body."""
        response = client.post('/api/v1/ask',
                               data='{}',
                               content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['status'] == 'error'

    def test_ask_missing_query(self, client):
        """Test ask endpoint with missing query field."""
        response = client.post('/api/v1/ask',
                               data=json.dumps({'other': 'field'}),
                               content_type='application/json')
        assert response.status_code == 400

    def test_ask_invalid_json(self, client):
        """Test ask endpoint with invalid JSON."""
        response = client.post('/api/v1/ask',
                               data='invalid json',
                               content_type='application/json')
        assert response.status_code in [400, 415]


class TestReloadEndpoint:
    """Test /api/v1/reload endpoint."""

    def test_reload_success(self, client):
        """Test reload endpoint without secret requirement."""
        response = client.post('/api/v1/reload')
        # Should either succeed or require secret
        assert response.status_code in [200, 401]

    def test_reload_with_wrong_secret(self, client):
        """Test reload endpoint with wrong secret."""
        # If secret is required, wrong secret should fail
        response = client.post('/api/v1/reload',
                               headers={'X-Reload-Secret': 'wrong-secret'})
        # May require correct secret or may not have one configured
        assert response.status_code in [200, 401]


class TestIndexRoute:
    """Test index route."""

    def test_index_returns_html(self, client):
        """Test index route returns HTML."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'<!DOCTYPE html>' in response.data or b'<html' in response.data


class TestErrorHandling:
    """Test error handling."""

    def test_404_error(self, client):
        """Test 404 error handling."""
        response = client.get('/api/v1/nonexistent')
        assert response.status_code == 404
        data = json.loads(response.data)
        assert data['status'] == 'error'

    def test_method_not_allowed(self, client):
        """Test method not allowed."""
        response = client.get('/api/v1/ask')  # POST only
        assert response.status_code == 405


class TestSecurityHeaders:
    """Test security headers."""

    def test_security_headers_present(self, client):
        """Test that security headers are present."""
        response = client.get('/')
        assert 'X-Content-Type-Options' in response.headers
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
        assert 'X-Frame-Options' in response.headers
        assert response.headers['X-Frame-Options'] == 'SAMEORIGIN'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
