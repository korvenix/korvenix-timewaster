from __future__ import annotations

from google.cloud import firestore


class FirestoreWrapper:
    """Thin wrapper around Firestore for Time Waster collections."""

    def __init__(self, client: firestore.Client) -> None:
        self._client = client

    # --- Config ---

    def get_config(self) -> dict:
        settings_doc = self._client.document("config/settings").get()
        title_costs_doc = self._client.document("config/titleCosts").get()
        user_overrides_doc = self._client.document("config/userOverrides").get()

        return {
            "titleCosts": title_costs_doc.to_dict() or {} if title_costs_doc.exists else {},
            "userOverrides": user_overrides_doc.to_dict() or {} if user_overrides_doc.exists else {},
            "settings": settings_doc.to_dict() or {"lateJoinerThresholdMins": 3, "enabled": True}
            if settings_doc.exists
            else {"lateJoinerThresholdMins": 3, "enabled": True},
        }

    def set_title_cost(self, title: str, hourly_rate: float) -> None:
        self._client.document("config/titleCosts").set(
            {title: hourly_rate}, merge=True
        )

    def set_user_override(self, email: str, hourly_rate: float) -> None:
        self._client.document("config/userOverrides").set(
            {email: hourly_rate}, merge=True
        )

    def delete_user_override(self, email: str) -> None:
        self._client.document("config/userOverrides").set(
            {email: firestore.DELETE_FIELD}, merge=True
        )

    def update_settings(self, settings: dict) -> None:
        self._client.document("config/settings").set(settings, merge=True)

    # --- Join Events ---

    def store_join_event(self, event_id: str, email: str, data: dict) -> None:
        doc_id = f"{event_id}_{email}"
        self._client.document(f"joinEvents/{doc_id}").set(data)

    def get_join_events_for_meeting(self, event_id: str) -> list[dict]:
        docs = (
            self._client.collection("joinEvents")
            .where("eventId", "==", event_id)
            .stream()
        )
        return [doc.to_dict() for doc in docs]

    def get_join_event(self, event_id: str, email: str) -> dict | None:
        doc_id = f"{event_id}_{email}"
        doc = self._client.document(f"joinEvents/{doc_id}").get()
        return doc.to_dict() if doc.exists else None

    # --- Meeting Reports ---

    def store_meeting_report(self, event_id: str, data: dict) -> None:
        self._client.document(f"meetingReports/{event_id}").set(data)

    def get_meeting_report(self, event_id: str) -> dict | None:
        doc = self._client.document(f"meetingReports/{event_id}").get()
        return doc.to_dict() if doc.exists else None

    def list_meeting_reports(
        self, limit: int = 50, start_after_date: str | None = None
    ) -> list[dict]:
        query = self._client.collection("meetingReports").order_by(
            "createdAt", direction=firestore.Query.DESCENDING
        )
        if start_after_date:
            query = query.where("createdAt", ">=", start_after_date)
        query = query.limit(limit)
        return [doc.to_dict() for doc in query.stream()]
