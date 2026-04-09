from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_oidc_token
from app.cost_engine import calculate_late_joiner_cost
from app.dependencies import get_firestore_client
from app.firestore_client import FirestoreWrapper
from app.models import JoinEventRequest

router = APIRouter(prefix="/api/join-events", tags=["join-events"])


def _get_store(client=Depends(get_firestore_client)) -> FirestoreWrapper:
    return FirestoreWrapper(client)


@router.post("", status_code=status.HTTP_201_CREATED)
def ingest_join_event(
    body: JoinEventRequest,
    claims: dict = Depends(verify_oidc_token),
    store: FirestoreWrapper = Depends(_get_store),
):
    """Ingest a join event from the Chrome extension.

    The email is extracted from the OIDC token claims, not the request body,
    to prevent spoofing.
    """
    email = claims.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OIDC token missing email claim",
        )

    config = store.get_config()
    threshold_mins = config["settings"].get("lateJoinerThresholdMins", 3)

    # We don't know waiting count or rates at ingestion time,
    # so store with zero costs — real-time endpoint calculates live.
    data = {
        "eventId": body.event_id,
        "email": email,
        "joinedAt": body.joined_at.isoformat(),
        "meetingStartAt": body.meeting_start_at.isoformat(),
        "lateMins": 0.0,
        "waitingCount": 0,
        "selfCost": 0.0,
        "opportunityCost": 0.0,
        "reportedToMeeting": False,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    store.store_join_event(body.event_id, email, data)

    return {"status": "ok", "eventId": body.event_id, "email": email}
