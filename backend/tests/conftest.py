"""Shared fixtures for tests."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_firestore_client, get_settings, get_calendar_service
from app.main import app
from app.settings import Settings


@pytest.fixture
def mock_settings():
    return Settings(
        gcp_project_id="test-project",
        allowed_hd_claim="korvenix.com",
        oidc_audience="test-audience",
        firestore_database="(default)",
        delegated_admin_email="admin@korvenix.com",
        admin_emails="alice@korvenix.com",
    )


@pytest.fixture
def mock_firestore():
    return MagicMock()


@pytest.fixture
def mock_calendar_service():
    return MagicMock()


@pytest.fixture
def valid_oidc_claims():
    return {
        "email": "alice@korvenix.com",
        "hd": "korvenix.com",
        "sub": "12345",
        "aud": "test-audience",
    }


@pytest.fixture
def client(mock_settings, mock_firestore, mock_calendar_service, valid_oidc_claims):
    """Test client with all external dependencies mocked."""

    app.dependency_overrides[get_settings] = lambda: mock_settings
    app.dependency_overrides[get_firestore_client] = lambda: mock_firestore
    app.dependency_overrides[get_calendar_service] = lambda: mock_calendar_service

    # Mock OIDC token verification globally
    with patch("app.auth.id_token.verify_oauth2_token", return_value=valid_oidc_claims):
        yield TestClient(app)

    app.dependency_overrides.clear()
