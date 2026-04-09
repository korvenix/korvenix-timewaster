"""Integration tests for API endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_calendar_service, get_firestore_client, get_settings
from app.main import app
from app.settings import Settings


@pytest.fixture
def scheduler_client(mock_firestore, mock_calendar_service):
    """Test client configured for Cloud Scheduler auth (sync-meeting endpoint)."""
    scheduler_settings = Settings(
        gcp_project_id="test-project",
        allowed_hd_claim="korvenix.com",
        oidc_audience="test-audience",
        scheduler_oidc_audience="test-scheduler-audience",
        scheduler_service_account_email="",
        firestore_database="(default)",
        delegated_admin_email="admin@korvenix.com",
        admin_emails="alice@korvenix.com",
    )
    scheduler_claims = {
        "email": "scheduler@sa.iam.gserviceaccount.com",
        "sub": "scheduler-sa",
    }

    app.dependency_overrides[get_settings] = lambda: scheduler_settings
    app.dependency_overrides[get_firestore_client] = lambda: mock_firestore
    app.dependency_overrides[get_calendar_service] = lambda: mock_calendar_service

    with patch("app.auth.id_token.verify_oauth2_token", return_value=scheduler_claims):
        yield TestClient(app)

    app.dependency_overrides.clear()


class TestHealthz:
    def test_healthz(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestConfigEndpoints:
    def test_get_config_empty(self, client, mock_firestore):
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_firestore.document.return_value.get.return_value = mock_doc

        resp = client.get("/api/config", headers={"Authorization": "Bearer test"})
        assert resp.status_code == 200
        data = resp.json()
        assert "titleCosts" in data
        assert "settings" in data

    def test_set_title_cost(self, client, mock_firestore):
        resp = client.patch(
            "/api/config/titles/Software%20Engineer",
            json={"hourlyRate": 150.0},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        assert resp.json()["hourlyRate"] == 150.0
        mock_firestore.document.assert_called()

    def test_set_user_override(self, client, mock_firestore):
        resp = client.patch(
            "/api/config/users/alice@korvenix.com",
            json={"hourlyRate": 200.0},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        assert resp.json()["hourlyRate"] == 200.0

    def test_delete_user_override(self, client, mock_firestore):
        resp = client.delete(
            "/api/config/users/alice@korvenix.com",
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["email"] == "alice@korvenix.com"
        from google.cloud import firestore

        mock_firestore.document.assert_called_with("config/userOverrides")
        mock_firestore.document("config/userOverrides").set.assert_called_once_with(
            {"alice@korvenix.com": firestore.DELETE_FIELD}, merge=True
        )

    def test_update_settings(self, client, mock_firestore):
        resp = client.patch(
            "/api/config/settings",
            json={"lateJoinerThresholdMins": 10},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        mock_firestore.document.assert_called_with("config/settings")
        mock_firestore.document("config/settings").set.assert_called_once_with(
            {"lateJoinerThresholdMins": 10}, merge=True
        )

    def test_update_settings_non_admin_forbidden(self, mock_firestore, mock_calendar_service):
        non_admin_settings = Settings(
            gcp_project_id="test-project",
            allowed_hd_claim="korvenix.com",
            oidc_audience="test-audience",
            admin_emails="admin@korvenix.com",
        )
        non_admin_claims = {"email": "alice@korvenix.com", "hd": "korvenix.com", "sub": "123"}
        app.dependency_overrides[get_settings] = lambda: non_admin_settings
        app.dependency_overrides[get_firestore_client] = lambda: mock_firestore
        with patch("app.auth.id_token.verify_oauth2_token", return_value=non_admin_claims):
            c = TestClient(app)
            resp = c.patch(
                "/api/config/settings",
                json={"lateJoinerThresholdMins": 10},
                headers={"Authorization": "Bearer test"},
            )
        app.dependency_overrides.clear()
        assert resp.status_code == 403

    def test_update_settings_negative_threshold_rejected(self, client):
        resp = client.patch(
            "/api/config/settings",
            json={"lateJoinerThresholdMins": -5},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 422

    def test_non_admin_delete_user_override_forbidden(self, client, mock_firestore):
        with patch(
            "app.auth.id_token.verify_oauth2_token",
            return_value={
                "email": "nonadmin@korvenix.com",
                "hd": "korvenix.com",
                "sub": "99999",
                "aud": "test-audience",
            },
        ):
            resp = client.delete(
                "/api/config/users/alice@korvenix.com",
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 403


class TestJoinEvents:
    def test_ingest_join_event(self, client, mock_firestore):
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "lateJoinerThresholdMins": 3,
            "enabled": True,
        }
        mock_firestore.document.return_value.get.return_value = mock_doc

        resp = client.post(
            "/api/join-events",
            json={
                "eventId": "event123",
                "joinedAt": "2026-01-01T10:02:00Z",
                "meetingStartAt": "2026-01-01T10:00:00Z",
            },
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 201
        assert resp.json()["email"] == "alice@korvenix.com"

    def test_ingest_join_event_missing_email_in_token(self, client, mock_firestore):
        """Token without email claim should be rejected."""
        with patch(
            "app.auth.id_token.verify_oauth2_token",
            return_value={"hd": "korvenix.com", "sub": "123"},
        ):
            mock_doc = MagicMock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = {
                "lateJoinerThresholdMins": 3,
                "enabled": True,
            }
            mock_firestore.document.return_value.get.return_value = mock_doc

            resp = client.post(
                "/api/join-events",
                json={
                    "eventId": "event123",
                    "joinedAt": "2026-01-01T10:02:00Z",
                    "meetingStartAt": "2026-01-01T10:00:00Z",
                },
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 400


class TestMeetingCost:
    def test_get_meeting_cost(self, client, mock_firestore, mock_calendar_service):
        # Mock config
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "lateJoinerThresholdMins": 3,
            "enabled": True,
        }

        mock_overrides_doc = MagicMock()
        mock_overrides_doc.exists = True
        mock_overrides_doc.to_dict.return_value = {"alice@korvenix.com": 150.0}

        mock_title_doc = MagicMock()
        mock_title_doc.exists = False

        def doc_side_effect(path):
            mock_ref = MagicMock()
            if path == "config/settings":
                mock_ref.get.return_value = mock_doc
            elif path == "config/titleCosts":
                mock_ref.get.return_value = mock_title_doc
            elif path == "config/userOverrides":
                mock_ref.get.return_value = mock_overrides_doc
            else:
                not_found = MagicMock()
                not_found.exists = False
                mock_ref.get.return_value = not_found
            return mock_ref

        mock_firestore.document.side_effect = doc_side_effect

        # Mock Calendar API
        mock_calendar_service.events.return_value.get.return_value.execute.return_value = {
            "attendees": [{"email": "alice@korvenix.com"}],
            "start": {"dateTime": "2026-01-01T10:00:00+00:00"},
            "end": {"dateTime": "2026-01-01T11:00:00+00:00"},
        }

        resp = client.get(
            "/api/meetings/event123/cost",
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "totalCost" in data
        assert "attendeeCosts" in data


class TestReports:
    def test_list_reports_empty(self, client, mock_firestore):
        mock_firestore.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = iter(
            []
        )
        resp = client.get(
            "/api/reports", headers={"Authorization": "Bearer test"}
        )
        assert resp.status_code == 200
        assert resp.json()["reports"] == []

    def test_get_report_not_found(self, client, mock_firestore):
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_firestore.document.return_value.get.return_value = mock_doc

        resp = client.get(
            "/api/reports/nonexistent", headers={"Authorization": "Bearer test"}
        )
        assert resp.status_code == 404

    def test_get_report_found(self, client, mock_firestore):
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "eventId": "event123",
            "totalCost": 480.0,
            "durationMins": 60.0,
            "createdAt": "2026-01-01T11:00:00+00:00",
            "attendees": [],
        }
        mock_firestore.document.return_value.get.return_value = mock_doc

        resp = client.get(
            "/api/reports/event123", headers={"Authorization": "Bearer test"}
        )
        assert resp.status_code == 200
        assert resp.json()["eventId"] == "event123"

    def test_get_report_invalid_event_id(self, client):
        # Backslash in event_id (URL-encoded) is caught by _validate_event_id → 400
        resp = client.get(
            "/api/reports/bad%5Cid", headers={"Authorization": "Bearer test"}
        )
        assert resp.status_code == 400

    def test_list_reports_with_pagination(self, client, mock_firestore):
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            "eventId": "e1",
            "totalCost": 100.0,
            "durationMins": 30.0,
            "createdAt": "2026-01-01T11:00:00+00:00",
            "attendees": [{"email": "a@b.com"}],
        }
        mock_firestore.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = iter(
            [mock_doc]
        )
        resp = client.get(
            "/api/reports?limit=10", headers={"Authorization": "Bearer test"}
        )
        assert resp.status_code == 200
        assert len(resp.json()["reports"]) == 1
        assert resp.json()["reports"][0]["attendeeCount"] == 1


class TestMeetingCostEdgeCases:
    def test_calendar_api_error_returns_502(self, client, mock_calendar_service):
        mock_calendar_service.events.return_value.get.return_value.execute.side_effect = Exception(
            "Calendar unavailable"
        )
        resp = client.get(
            "/api/meetings/event123/cost",
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 502
        assert "calendar" in resp.json()["detail"].lower()

    def test_event_with_no_start_returns_404(self, client, mock_calendar_service):
        # start/end missing dateTime → get_event_attendees returns "" → not "" is True → 404
        mock_calendar_service.events.return_value.get.return_value.execute.return_value = {
            "attendees": [{"email": "alice@korvenix.com"}],
            "start": {},
            "end": {},
        }
        resp = client.get(
            "/api/meetings/event123/cost",
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 404

    def test_invalid_event_id_returns_400(self, client):
        # Backslash in event_id (URL-encoded) is caught by _validate_event_id → 400
        resp = client.get(
            "/api/meetings/bad%5Cevent/cost",
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 400


class TestConfigValidation:
    def test_negative_title_rate_rejected(self, client):
        resp = client.patch(
            "/api/config/titles/Engineer",
            json={"hourlyRate": -50.0},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 422

    def test_negative_user_rate_rejected(self, client):
        resp = client.patch(
            "/api/config/users/alice@korvenix.com",
            json={"hourlyRate": -1.0},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 422

    def test_non_admin_title_update_forbidden(self, mock_firestore, mock_calendar_service):
        non_admin_settings = Settings(
            gcp_project_id="test-project",
            allowed_hd_claim="korvenix.com",
            oidc_audience="test-audience",
            admin_emails="admin@korvenix.com",  # alice is not admin
        )
        non_admin_claims = {"email": "alice@korvenix.com", "hd": "korvenix.com", "sub": "123"}

        app.dependency_overrides[get_settings] = lambda: non_admin_settings
        app.dependency_overrides[get_firestore_client] = lambda: mock_firestore

        with patch("app.auth.id_token.verify_oauth2_token", return_value=non_admin_claims):
            c = TestClient(app)
            resp = c.patch(
                "/api/config/titles/Engineer",
                json={"hourlyRate": 150.0},
                headers={"Authorization": "Bearer test"},
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 403

    def test_zero_rate_accepted(self, client, mock_firestore):
        resp = client.patch(
            "/api/config/titles/Intern",
            json={"hourlyRate": 0.0},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200


class TestJoinEventEdgeCases:
    def test_duplicate_join_is_idempotent(self, client, mock_firestore):
        """Posting the same join event twice should succeed both times (last write wins)."""
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"lateJoinerThresholdMins": 3, "enabled": True}
        mock_firestore.document.return_value.get.return_value = mock_doc

        payload = {
            "eventId": "event123",
            "joinedAt": "2026-01-01T10:02:00Z",
            "meetingStartAt": "2026-01-01T10:00:00Z",
        }
        headers = {"Authorization": "Bearer test"}

        resp1 = client.post("/api/join-events", json=payload, headers=headers)
        resp2 = client.post("/api/join-events", json=payload, headers=headers)
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["email"] == resp2.json()["email"]

    def test_invalid_event_id_rejected(self, client):
        """event_id with path separator is rejected at Pydantic validation."""
        resp = client.post(
            "/api/join-events",
            json={
                "eventId": "bad/event",
                "joinedAt": "2026-01-01T10:02:00Z",
                "meetingStartAt": "2026-01-01T10:00:00Z",
            },
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 422


class TestSyncMeeting:
    def _calendar_mock(self, mock_calendar_service, event_data: dict):
        mock_calendar_service.events.return_value.get.return_value.execute.return_value = event_data

    def _firestore_config(self, mock_firestore):
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"lateJoinerThresholdMins": 3, "enabled": True}

        mock_overrides = MagicMock()
        mock_overrides.exists = False

        mock_title = MagicMock()
        mock_title.exists = False

        mock_join = MagicMock()
        mock_join.exists = False

        def doc_side_effect(path):
            ref = MagicMock()
            if "settings" in path:
                ref.get.return_value = mock_doc
            else:
                not_found = MagicMock()
                not_found.exists = False
                ref.get.return_value = not_found
            return ref

        mock_firestore.document.side_effect = doc_side_effect

    def test_sync_meeting_success(self, scheduler_client, mock_firestore, mock_calendar_service):
        self._calendar_mock(
            mock_calendar_service,
            {
                "attendees": [{"email": "alice@korvenix.com"}],
                "start": {"dateTime": "2026-01-01T10:00:00+00:00"},
                "end": {"dateTime": "2026-01-01T11:00:00+00:00"},
            },
        )
        self._firestore_config(mock_firestore)

        resp = scheduler_client.post(
            "/api/internal/sync-meeting",
            json={"eventId": "event123"},
            headers={"Authorization": "Bearer scheduler-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["eventId"] == "event123"
        mock_firestore.document.assert_called()

    def test_sync_meeting_idempotent(self, scheduler_client, mock_firestore, mock_calendar_service):
        """Running sync twice should both succeed (last write wins)."""
        event_data = {
            "attendees": [{"email": "alice@korvenix.com"}],
            "start": {"dateTime": "2026-01-01T10:00:00+00:00"},
            "end": {"dateTime": "2026-01-01T11:00:00+00:00"},
        }
        self._calendar_mock(mock_calendar_service, event_data)
        self._firestore_config(mock_firestore)

        headers = {"Authorization": "Bearer scheduler-token"}
        resp1 = scheduler_client.post(
            "/api/internal/sync-meeting", json={"eventId": "event123"}, headers=headers
        )
        resp2 = scheduler_client.post(
            "/api/internal/sync-meeting", json={"eventId": "event123"}, headers=headers
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["totalCost"] == resp2.json()["totalCost"]

    def test_sync_calendar_error_returns_502(self, scheduler_client, mock_calendar_service):
        mock_calendar_service.events.return_value.get.return_value.execute.side_effect = Exception(
            "Calendar down"
        )
        resp = scheduler_client.post(
            "/api/internal/sync-meeting",
            json={"eventId": "event123"},
            headers={"Authorization": "Bearer scheduler-token"},
        )
        assert resp.status_code == 502

    def test_sync_event_no_times_returns_skipped(
        self, scheduler_client, mock_firestore, mock_calendar_service
    ):
        # start/end with no dateTime → get_event_attendees returns "" → sync returns skipped
        self._calendar_mock(
            mock_calendar_service,
            {"attendees": [], "start": {}, "end": {}},
        )
        self._firestore_config(mock_firestore)

        resp = scheduler_client.post(
            "/api/internal/sync-meeting",
            json={"eventId": "event123"},
            headers={"Authorization": "Bearer scheduler-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "skipped"

    def test_sync_invalid_event_id_rejected(self, scheduler_client):
        """event_id with path separator rejected by Pydantic."""
        resp = scheduler_client.post(
            "/api/internal/sync-meeting",
            json={"eventId": "bad/event"},
            headers={"Authorization": "Bearer scheduler-token"},
        )
        assert resp.status_code == 422
