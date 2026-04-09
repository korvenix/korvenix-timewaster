"""Tests for OIDC authentication middleware."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_settings
from app.main import app
from app.settings import Settings


@pytest.fixture
def mock_settings():
    return Settings(
        gcp_project_id="test-project",
        allowed_hd_claim="korvenix.com",
        oidc_audience="test-audience",
    )


@pytest.fixture
def base_client(mock_settings):
    app.dependency_overrides[get_settings] = lambda: mock_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestOIDCAuth:
    def test_missing_auth_header(self, base_client):
        resp = base_client.get("/api/config")
        assert resp.status_code == 401
        assert "Missing or malformed" in resp.json()["detail"]

    def test_malformed_auth_header(self, base_client):
        resp = base_client.get("/api/config", headers={"Authorization": "Basic abc"})
        assert resp.status_code == 401

    def test_invalid_token(self, base_client):
        with patch(
            "app.auth.id_token.verify_oauth2_token",
            side_effect=ValueError("bad token"),
        ):
            resp = base_client.get(
                "/api/config", headers={"Authorization": "Bearer bad-token"}
            )
            assert resp.status_code == 401
            assert "Invalid OIDC token" in resp.json()["detail"]

    def test_wrong_hd_claim(self, base_client):
        claims = {"email": "evil@attacker.com", "hd": "attacker.com", "sub": "666"}
        with patch("app.auth.id_token.verify_oauth2_token", return_value=claims):
            resp = base_client.get(
                "/api/config", headers={"Authorization": "Bearer valid-token"}
            )
            assert resp.status_code == 403
            assert "hd claim" in resp.json()["detail"]

    def test_valid_token_accepted(self, base_client):
        claims = {"email": "alice@korvenix.com", "hd": "korvenix.com", "sub": "123"}
        mock_fs = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_fs.document.return_value.get.return_value = mock_doc

        from app.dependencies import get_firestore_client

        app.dependency_overrides[get_firestore_client] = lambda: mock_fs

        with patch("app.auth.id_token.verify_oauth2_token", return_value=claims):
            resp = base_client.get(
                "/api/config", headers={"Authorization": "Bearer valid-token"}
            )
            assert resp.status_code == 200

        app.dependency_overrides.clear()
