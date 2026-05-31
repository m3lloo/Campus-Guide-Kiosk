"""
Pytest configuration and fixtures for Campus Guide Kiosk tests.
"""

import pytest
from unittest.mock import patch, MagicMock
import os
import sys

# Ensure the project root is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment variables."""
    os.environ["ENVIRONMENT"] = "testing"
    os.environ["LOG_LEVEL"] = "DEBUG"
    os.environ["RATE_LIMIT_ENABLED"] = "False"
    yield


@pytest.fixture
def mock_firebase():
    """Mock Firebase client."""
    with patch("firebase_admin._apps", []):
        with patch("firebase_admin.initialize_app"):
            with patch("firebase_admin.credentials.Certificate"):
                mock_db = MagicMock()
                with patch("firebase_admin.firestore.client", return_value=mock_db):
                    yield mock_db


@pytest.fixture
def mock_embeddings():
    """Mock embedding model."""
    mock_model = MagicMock()
    mock_model.encode.return_value = [0.1] * 384
    return mock_model
