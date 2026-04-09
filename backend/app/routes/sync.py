from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.auth import verify_scheduler_oidc_token
from app.cost_engine import calculate_meeting_cost
from app.dependencies import get_calendar_service, get_firestore_client
from app.firestore_client import FirestoreWrapper
from app.google_apis import CalendarAPI
from app.models import _validate_event_id

router = APIRouter(prefix="/api/internal", tags=["internal"])


class SyncMeetingRequest(BaseModel):
    event_id: str = Field(alias="eventId")
    conference_id: str | None = Field(default=None, alias="conferenceId")

    model_config = {"populate_by_name": True}

    @field_validator("event_id")
    @classmethod
    def no_path_separators(cls, v: str) -> str:
        return _validate_event_id(v)


def _get_store(client=Depends(get_firestore_client)) -> FirestoreWrapper:
    return FirestoreWrapper(client)


def _get_calendar_api(service=Depends(get_calendar_service)) -> CalendarAPI:
    return CalendarAPI(service)


@router.post("/sync-meeting")
def sync_meeting(
    body: SyncMeetingRequest,
    _scheduler_claims: dict = Depends(verify_scheduler_oidc_token),
    store: FirestoreWrapper = Depends(_get_store),
    calendar_api: CalendarAPI = Depends(_get_calendar_api),
):
    """Invoked by Cloud Scheduler to reconcile a completed meeting.

    Fetches Calendar event data, merges with stored join events,
    calculates final costs, and writes the meeting report.

    Authentication: Cloud Scheduler OIDC token verified via verify_scheduler_oidc_token.
    """
    event_id = body.event_id

    # Fetch event from Calendar API
    try:
        event_data = calendar_api.get_event_attendees(
            calendar_id="primary", event_id=event_id
        )
    except Exception:
        # C7 fix: do not leak internal exception details to callers.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch calendar event",
        )

    if not event_data["start"] or not event_data["end"]:
        return {"status": "skipped", "reason": "no start/end time"}

    scheduled_start = datetime.fromisoformat(event_data["start"])
    scheduled_end = datetime.fromisoformat(event_data["end"])

    config = store.get_config()
    threshold_mins = config["settings"].get("lateJoinerThresholdMins", 3)
    user_overrides = config.get("userOverrides", {})
    default_rate = 100.0

    # Build attendees from Calendar + stored join events
    attendees = []
    for a in event_data["attendees"]:
        email = a["email"]
        rate = user_overrides.get(email, default_rate)
        join_event = store.get_join_event(event_id, email)
        joined_at = None
        if join_event and join_event.get("joinedAt"):
            joined_at = datetime.fromisoformat(join_event["joinedAt"])
        attendees.append({"email": email, "rate": rate, "joined_at": joined_at})

    result = calculate_meeting_cost(
        attendees=attendees,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        threshold_mins=threshold_mins,
    )

    duration_mins = (scheduled_end - scheduled_start).total_seconds() / 60.0

    report = {
        "eventId": event_id,
        "totalCost": result["total_cost"],
        "durationMins": round(duration_mins, 2),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "attendees": result["attendee_costs"],
    }

    store.store_meeting_report(event_id, report)

    return {"status": "ok", "eventId": event_id, "totalCost": result["total_cost"]}
