from __future__ import annotations

import time
from typing import Any

from cachetools import TTLCache


class CalendarAPI:
    """Wrapper for Google Calendar API v3."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def get_event_attendees(self, calendar_id: str, event_id: str) -> dict:
        """Fetch attendee list and event times for a calendar event.

        Returns:
            {
                "attendees": [{"email": str, "responseStatus": str}, ...],
                "start": str (ISO datetime),
                "end": str (ISO datetime),
            }
        """
        event = (
            self._service.events()
            .get(calendarId=calendar_id, eventId=event_id)
            .execute()
        )
        attendees = event.get("attendees", [])
        start = event.get("start", {}).get("dateTime", "")
        end = event.get("end", {}).get("dateTime", "")

        return {
            "attendees": [
                {"email": a["email"], "responseStatus": a.get("responseStatus", "needsAction")}
                for a in attendees
            ],
            "start": start,
            "end": end,
        }


class AdminDirectoryAPI:
    """Wrapper for Google Admin SDK Directory API with title caching."""

    def __init__(self, service: Any, cache_ttl_seconds: int = 3600) -> None:
        self._service = service
        self._cache: TTLCache = TTLCache(maxsize=10000, ttl=cache_ttl_seconds)

    def resolve_title(self, email: str) -> str | None:
        """Resolve an email to a Google Workspace job title.

        Returns the job title string, or None if not found.
        Uses a TTL cache to avoid repeated API calls.
        Implements exponential backoff on quota errors.
        """
        cached = self._cache.get(email)
        if cached is not None:
            return cached if cached != "__NOT_FOUND__" else None

        max_retries = 3
        for attempt in range(max_retries):
            try:
                user = (
                    self._service.users()
                    .get(userKey=email, projection="full")
                    .execute()
                )
                organizations = user.get("organizations", [])
                title = None
                for org in organizations:
                    if org.get("primary", False) or not title:
                        title = org.get("title")

                self._cache[email] = title if title else "__NOT_FOUND__"
                return title
            except Exception as exc:
                error_str = str(exc)
                if "quota" in error_str.lower() or "429" in error_str:
                    wait = (2**attempt) * 0.5
                    time.sleep(wait)
                    continue
                self._cache[email] = "__NOT_FOUND__"
                return None

        self._cache[email] = "__NOT_FOUND__"
        return None


class MeetAPI:
    """Wrapper for Google Meet REST API v2."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def get_meeting_participants(self, conference_id: str) -> list[dict]:
        """Fetch historical participant join/leave timestamps.

        Returns:
            [{"email": str, "joinedAt": str, "leftAt": str}, ...]
        """
        participants = []
        page_token = None

        while True:
            response = (
                self._service.conferenceRecords()
                .participants()
                .list(
                    parent=f"conferenceRecords/{conference_id}",
                    pageToken=page_token,
                )
                .execute()
            )

            for p in response.get("participants", []):
                email = p.get("signedinUser", {}).get("user", "")
                # Extract earliest session start and latest session end
                sessions = p.get("participantSessions", [])
                if not sessions:
                    joined_at = p.get("earliestStartTime", "")
                    left_at = p.get("latestEndTime", "")
                else:
                    joined_at = min(
                        (s.get("startTime", "") for s in sessions), default=""
                    )
                    left_at = max(
                        (s.get("endTime", "") for s in sessions), default=""
                    )

                participants.append(
                    {"email": email, "joinedAt": joined_at, "leftAt": left_at}
                )

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return participants
