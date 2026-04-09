from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import verify_oidc_token
from app.dependencies import get_firestore_client
from app.firestore_client import FirestoreWrapper
from app.models import _validate_event_id

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _get_store(client=Depends(get_firestore_client)) -> FirestoreWrapper:
    return FirestoreWrapper(client)


@router.get("")
def list_reports(
    _claims: dict = Depends(verify_oidc_token),
    store: FirestoreWrapper = Depends(_get_store),
    limit: int = Query(default=50, ge=1, le=200),
    after: str | None = Query(default=None, description="ISO date to filter from"),
):
    """List meeting cost reports, paginated, filterable by date."""
    reports = store.list_meeting_reports(limit=limit, start_after_date=after)
    items = []
    for r in reports:
        items.append(
            {
                "eventId": r.get("eventId", ""),
                "totalCost": r.get("totalCost", 0.0),
                "durationMins": r.get("durationMins", 0.0),
                "createdAt": r.get("createdAt", ""),
                "attendeeCount": len(r.get("attendees", [])),
            }
        )
    return {"reports": items}


@router.get("/{event_id}")
def get_report(
    event_id: str,
    _claims: dict = Depends(verify_oidc_token),
    store: FirestoreWrapper = Depends(_get_store),
):
    """Get a single meeting cost report."""
    # C3-RESIDUAL fix: validate path parameter against Firestore path injection
    try:
        _validate_event_id(event_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid event_id",
        )

    report = store.get_meeting_report(event_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No report found for event {event_id}",
        )
    return report
