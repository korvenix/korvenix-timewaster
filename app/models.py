from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ConfigSettings(BaseModel):
    late_joiner_threshold_mins: int = Field(default=3, alias="lateJoinerThresholdMins")
    enabled: bool = True


class ConfigResponse(BaseModel):
    title_costs: dict[str, float] = Field(default_factory=dict, alias="titleCosts")
    user_overrides: dict[str, float] = Field(default_factory=dict, alias="userOverrides")
    settings: ConfigSettings = Field(default_factory=ConfigSettings)

    model_config = {"populate_by_name": True}


def _validate_event_id(v: str) -> str:
    """Reject event_id values that contain Firestore path separators (C3 fix)."""
    if "/" in v or "\\" in v:
        raise ValueError("event_id must not contain path separators")
    return v


class SettingsUpdate(BaseModel):
    late_joiner_threshold_mins: int | None = Field(default=None, alias="lateJoinerThresholdMins", ge=0)
    enabled: bool | None = None

    model_config = {"populate_by_name": True}


class TitleCostUpdate(BaseModel):
    # C6 fix: ge=0 prevents negative hourly rates producing negative costs.
    hourly_rate: float = Field(alias="hourlyRate", ge=0)

    model_config = {"populate_by_name": True}


class UserCostUpdate(BaseModel):
    # C6 fix: ge=0 prevents negative hourly rates producing negative costs.
    hourly_rate: float = Field(alias="hourlyRate", ge=0)

    model_config = {"populate_by_name": True}


class JoinEventRequest(BaseModel):
    event_id: str = Field(alias="eventId")
    joined_at: datetime = Field(alias="joinedAt")
    meeting_start_at: datetime = Field(alias="meetingStartAt")

    model_config = {"populate_by_name": True}

    @field_validator("event_id")
    @classmethod
    def no_path_separators(cls, v: str) -> str:
        return _validate_event_id(v)


class Attendee(BaseModel):
    email: str
    rate: float
    joined_at: datetime | None = Field(default=None, alias="joinedAt")

    model_config = {"populate_by_name": True}


class AttendeeCost(BaseModel):
    email: str
    rate: float
    joined_at: datetime | None = Field(default=None, alias="joinedAt")
    late_mins: float = Field(alias="lateMins")
    self_cost: float = Field(alias="selfCost")
    opportunity_cost: float = Field(alias="opportunityCost")

    model_config = {"populate_by_name": True}


class MeetingCostResponse(BaseModel):
    total_cost: float = Field(alias="totalCost")
    attendee_costs: list[AttendeeCost] = Field(alias="attendeeCosts")

    model_config = {"populate_by_name": True}


class MeetingReportResponse(BaseModel):
    event_id: str = Field(alias="eventId")
    total_cost: float = Field(alias="totalCost")
    duration_mins: float = Field(alias="durationMins")
    created_at: datetime = Field(alias="createdAt")
    attendees: list[AttendeeCost]

    model_config = {"populate_by_name": True}


class MeetingReportListItem(BaseModel):
    event_id: str = Field(alias="eventId")
    total_cost: float = Field(alias="totalCost")
    duration_mins: float = Field(alias="durationMins")
    created_at: datetime = Field(alias="createdAt")
    attendee_count: int = Field(alias="attendeeCount")

    model_config = {"populate_by_name": True}
