from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_oidc_token
from app.cost_engine import calculate_meeting_cost
from app.dependencies import get_calendar_service, get_firestore_client
from app.firestore_client import FirestoreWrapper
from app.google_apis import CalendarAPI
from app.models import MeetingCostResponse, _validate_event_id

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


def _get_store(client=Depends(get_firestore_client)) -> FirestoreWrapper:
    return FirestoreWrapper(client)


def _get_calendar_api(service=Depends(get_calendar_service)) -> CalendarAPI:
    return CalendarAPI(service)


@router.get("/{event_id}/cost", response_model=MeetingCostResponse)
def get_meeting_cost(
    event_id: str,
    _claims: dict = Depends(verify_oidc_token),
    store: FirestoreWrapper = Depends(_get_store),
    calendar_api: CalendarAPI = Depends(_get_calendar_api),
):
    """Real-time cost estimate for a meeting in progress.

    Combines Calendar API attendee data with stored join events
    and config rates to produce a live cost estimate.
    """
    # C3-RESIDUAL fix: validate path parameter against Firestore path injection
    try:
        _validate_event_id(event_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid event_id",
        )

    config = store.get_config()
    threshold_mins = config["settings"].get("lateJoinerThresholdMins", 3)
    title_costs = config.get("titleCosts", {})
    user_overrides = config.get("userOverrides", {})
    default_rate = 100.0  # fallback hourly rate

    # Fetch event details from Calendar API
    try:
        event_data = calendar_api.get_event_attendees(
            calendar_id="primary", event_id=event_id
        )
    except Exception:
        # C7 fix: do not leak internal exception details (API keys, URLs) to callers.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch calendar event",
        )

    if not event_data["start"] or not event_data["end"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event has no start/end time (may be an all-day event)",
        )

    scheduled_start = datetime.fromisoformat(event_data["start"])
    scheduled_end = datetime.fromisoformat(event_data["end"])

    # Build attendee list with rates from config
    attendees = []
    for a in event_data["attendees"]:
        email = a["email"]
        rate = user_overrides.get(email, default_rate)
        # title-based rate lookup would require Admin SDK call here;
        # for real-time we use config-cached rates
        join_event = store.get_join_event(event_id, email)
        joined_at = None
        if join_event and join_event.get("joinedAt"):
            joined_at = datetime.fromisoformat(join_event["joinedAt"])

        attendees.append(
            {"email": email, "rate": rate, "joined_at": joined_at}
        )

    result = calculate_meeting_cost(
        attendees=attendees,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        threshold_mins=threshold_mins,
    )

    return result
