from __future__ import annotations

from datetime import datetime


def calculate_late_joiner_cost(
    joined_at: datetime,
    scheduled_start: datetime,
    threshold_mins: int,
    joiner_rate: float,
    avg_waiting_rate: float,
    waiting_count: int,
) -> dict:
    """Calculate the cost of a late joiner.

    Returns dict with keys: late_mins, self_cost, opportunity_cost.

    - late_mins: minutes late beyond the threshold (0 if not late)
    - self_cost: the joiner's own wasted time cost
    - opportunity_cost: cost imposed on others who were waiting
    """
    if threshold_mins < 0:
        threshold_mins = 0
    if waiting_count < 0:
        waiting_count = 0

    delay_seconds = (joined_at - scheduled_start).total_seconds()
    delay_mins = delay_seconds / 60.0

    late_mins = max(0.0, delay_mins - threshold_mins)

    if late_mins == 0:
        return {"late_mins": 0.0, "self_cost": 0.0, "opportunity_cost": 0.0}

    late_hours = late_mins / 60.0
    self_cost = round(late_hours * joiner_rate, 2)
    opportunity_cost = round(late_hours * avg_waiting_rate * waiting_count, 2)

    return {
        "late_mins": round(late_mins, 2),
        "self_cost": self_cost,
        "opportunity_cost": opportunity_cost,
    }


def calculate_meeting_cost(
    attendees: list[dict],
    scheduled_start: datetime,
    scheduled_end: datetime,
    threshold_mins: int,
) -> dict:
    """Calculate the total cost of a meeting.

    Each attendee dict must have keys: email, rate, joined_at (datetime or None).

    Returns dict with keys: total_cost, attendee_costs (list).
    """
    if not attendees:
        return {"total_cost": 0.0, "attendee_costs": []}

    duration_seconds = (scheduled_end - scheduled_start).total_seconds()
    duration_hours = max(0.0, duration_seconds / 3600.0)

    rates = [a["rate"] for a in attendees if a["rate"] > 0]
    avg_rate = sum(rates) / len(rates) if rates else 0.0

    attendee_costs = []
    total_cost = 0.0

    for attendee in attendees:
        email = attendee["email"]
        rate = attendee["rate"]
        joined_at = attendee.get("joined_at")

        base_cost = round(duration_hours * rate, 2)

        if joined_at is not None:
            others_present_before = sum(
                1
                for other in attendees
                if other["email"] != email
                and other.get("joined_at") is not None
                and other["joined_at"] <= scheduled_start
            )

            late_result = calculate_late_joiner_cost(
                joined_at=joined_at,
                scheduled_start=scheduled_start,
                threshold_mins=threshold_mins,
                joiner_rate=rate,
                avg_waiting_rate=avg_rate,
                waiting_count=others_present_before,
            )
        else:
            late_result = {"late_mins": 0.0, "self_cost": 0.0, "opportunity_cost": 0.0}

        entry_cost = base_cost + late_result["self_cost"] + late_result["opportunity_cost"]
        total_cost += entry_cost

        attendee_costs.append(
            {
                "email": email,
                "rate": rate,
                "joinedAt": joined_at.isoformat() if joined_at else None,
                "lateMins": late_result["late_mins"],
                "selfCost": late_result["self_cost"],
                "opportunityCost": late_result["opportunity_cost"],
            }
        )

    return {
        "total_cost": round(total_cost, 2),
        "attendee_costs": attendee_costs,
    }
