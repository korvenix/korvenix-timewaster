"""Tests for the cost calculation engine — targeting 100% branch coverage."""

from datetime import datetime, timezone

import pytest

from app.cost_engine import calculate_late_joiner_cost, calculate_meeting_cost


# --- calculate_late_joiner_cost ---


class TestCalculateLateJoinerCost:
    def test_not_late_within_threshold(self):
        """Joiner arrives 2 min after start with 3 min threshold = not late."""
        result = calculate_late_joiner_cost(
            joined_at=datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc),
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            threshold_mins=3,
            joiner_rate=150.0,
            avg_waiting_rate=120.0,
            waiting_count=4,
        )
        assert result["late_mins"] == 0.0
        assert result["self_cost"] == 0.0
        assert result["opportunity_cost"] == 0.0

    def test_on_time_exactly_at_start(self):
        """Joiner arrives exactly at scheduled start."""
        result = calculate_late_joiner_cost(
            joined_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            threshold_mins=3,
            joiner_rate=150.0,
            avg_waiting_rate=120.0,
            waiting_count=4,
        )
        assert result["late_mins"] == 0.0

    def test_early_joiner(self):
        """Joiner arrives before scheduled start."""
        result = calculate_late_joiner_cost(
            joined_at=datetime(2026, 1, 1, 9, 55, tzinfo=timezone.utc),
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            threshold_mins=3,
            joiner_rate=150.0,
            avg_waiting_rate=120.0,
            waiting_count=4,
        )
        assert result["late_mins"] == 0.0

    def test_exactly_at_threshold(self):
        """Joiner arrives exactly at threshold boundary = not late."""
        result = calculate_late_joiner_cost(
            joined_at=datetime(2026, 1, 1, 10, 3, tzinfo=timezone.utc),
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            threshold_mins=3,
            joiner_rate=150.0,
            avg_waiting_rate=120.0,
            waiting_count=4,
        )
        assert result["late_mins"] == 0.0

    def test_late_beyond_threshold(self):
        """Joiner arrives 7 min after start with 3 min threshold = 4 min late."""
        result = calculate_late_joiner_cost(
            joined_at=datetime(2026, 1, 1, 10, 7, tzinfo=timezone.utc),
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            threshold_mins=3,
            joiner_rate=150.0,
            avg_waiting_rate=120.0,
            waiting_count=4,
        )
        assert result["late_mins"] == 4.0
        # self_cost = (4/60) * 150 = 10.0
        assert result["self_cost"] == 10.0
        # opportunity_cost = (4/60) * 120 * 4 = 32.0
        assert result["opportunity_cost"] == 32.0

    def test_zero_threshold(self):
        """Any delay counts as late when threshold is 0."""
        result = calculate_late_joiner_cost(
            joined_at=datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc),
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            threshold_mins=0,
            joiner_rate=100.0,
            avg_waiting_rate=100.0,
            waiting_count=2,
        )
        assert result["late_mins"] == 1.0
        assert result["self_cost"] == round(1 / 60 * 100, 2)

    def test_negative_threshold_treated_as_zero(self):
        """Negative threshold is clamped to 0."""
        result = calculate_late_joiner_cost(
            joined_at=datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc),
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            threshold_mins=-5,
            joiner_rate=100.0,
            avg_waiting_rate=100.0,
            waiting_count=1,
        )
        assert result["late_mins"] == 2.0

    def test_negative_waiting_count_treated_as_zero(self):
        """Negative waiting count is clamped to 0."""
        result = calculate_late_joiner_cost(
            joined_at=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc),
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            threshold_mins=0,
            joiner_rate=100.0,
            avg_waiting_rate=100.0,
            waiting_count=-3,
        )
        # waiting_count clamped to 0, so opportunity_cost = 0
        assert result["opportunity_cost"] == 0.0

    def test_zero_joiner_rate(self):
        """Zero joiner rate means zero self cost."""
        result = calculate_late_joiner_cost(
            joined_at=datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc),
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            threshold_mins=3,
            joiner_rate=0.0,
            avg_waiting_rate=100.0,
            waiting_count=3,
        )
        assert result["self_cost"] == 0.0
        assert result["opportunity_cost"] > 0.0

    def test_zero_waiting_count(self):
        """Nobody waiting = zero opportunity cost."""
        result = calculate_late_joiner_cost(
            joined_at=datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc),
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            threshold_mins=3,
            joiner_rate=150.0,
            avg_waiting_rate=120.0,
            waiting_count=0,
        )
        assert result["self_cost"] > 0.0
        assert result["opportunity_cost"] == 0.0


# --- calculate_meeting_cost ---


class TestCalculateMeetingCost:
    def test_empty_attendees(self):
        """No attendees = zero cost."""
        result = calculate_meeting_cost(
            attendees=[],
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
            threshold_mins=3,
        )
        assert result["total_cost"] == 0.0
        assert result["attendee_costs"] == []

    def test_single_attendee_no_join_time(self):
        """Single attendee without join data — base cost only."""
        result = calculate_meeting_cost(
            attendees=[{"email": "alice@co.com", "rate": 120.0}],
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
            threshold_mins=3,
        )
        # 1 hour * $120 = $120
        assert result["total_cost"] == 120.0
        assert len(result["attendee_costs"]) == 1
        assert result["attendee_costs"][0]["lateMins"] == 0.0

    def test_single_attendee_with_join_on_time(self):
        """Single attendee who joined on time."""
        result = calculate_meeting_cost(
            attendees=[
                {
                    "email": "alice@co.com",
                    "rate": 120.0,
                    "joined_at": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
                }
            ],
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
            threshold_mins=3,
        )
        assert result["total_cost"] == 120.0
        assert result["attendee_costs"][0]["lateMins"] == 0.0

    def test_late_joiner_with_others_waiting(self):
        """One late joiner with two others who joined on time."""
        result = calculate_meeting_cost(
            attendees=[
                {
                    "email": "alice@co.com",
                    "rate": 150.0,
                    "joined_at": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
                },
                {
                    "email": "bob@co.com",
                    "rate": 150.0,
                    "joined_at": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
                },
                {
                    "email": "charlie@co.com",
                    "rate": 150.0,
                    "joined_at": datetime(2026, 1, 1, 10, 7, tzinfo=timezone.utc),
                },
            ],
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
            threshold_mins=3,
        )
        # Base cost: 3 * 150 * 1 = 450
        # Charlie is 4 min late: self_cost = (4/60)*150 = 10, opp = (4/60)*150*2 = 20
        # Total = 450 + 10 + 20 = 480
        assert result["total_cost"] == 480.0

        charlie = [c for c in result["attendee_costs"] if c["email"] == "charlie@co.com"][0]
        assert charlie["lateMins"] == 4.0
        assert charlie["selfCost"] == 10.0
        assert charlie["opportunityCost"] == 20.0

    def test_zero_duration_meeting(self):
        """Meeting with zero duration — base cost is 0, but late costs still apply."""
        result = calculate_meeting_cost(
            attendees=[
                {
                    "email": "alice@co.com",
                    "rate": 150.0,
                    "joined_at": datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc),
                },
            ],
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            threshold_mins=3,
        )
        # Base cost = 0 (zero duration)
        # Late: 2 min late, self_cost = (2/60)*150 = 5
        assert result["attendee_costs"][0]["lateMins"] == 2.0
        assert result["attendee_costs"][0]["selfCost"] == 5.0

    def test_all_attendees_late(self):
        """All attendees join late — no one was 'waiting' at start."""
        result = calculate_meeting_cost(
            attendees=[
                {
                    "email": "alice@co.com",
                    "rate": 120.0,
                    "joined_at": datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc),
                },
                {
                    "email": "bob@co.com",
                    "rate": 120.0,
                    "joined_at": datetime(2026, 1, 1, 10, 6, tzinfo=timezone.utc),
                },
            ],
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
            threshold_mins=3,
        )
        # Both are late, but neither joined at or before start, so waiting_count = 0 for both
        for ac in result["attendee_costs"]:
            assert ac["opportunityCost"] == 0.0

    def test_attendee_with_zero_rate(self):
        """Attendee with rate 0 contributes no cost."""
        result = calculate_meeting_cost(
            attendees=[
                {"email": "intern@co.com", "rate": 0.0, "joined_at": None},
                {
                    "email": "boss@co.com",
                    "rate": 200.0,
                    "joined_at": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
                },
            ],
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
            threshold_mins=3,
        )
        # avg_rate computed from non-zero only: 200
        # intern: base = 0
        # boss: base = 200
        assert result["total_cost"] == 200.0

    def test_mixed_join_times(self):
        """Mix of on-time, late, and no-join-data attendees."""
        result = calculate_meeting_cost(
            attendees=[
                {
                    "email": "a@co.com",
                    "rate": 100.0,
                    "joined_at": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
                },
                {"email": "b@co.com", "rate": 100.0},  # no joined_at key at all
                {
                    "email": "c@co.com",
                    "rate": 100.0,
                    "joined_at": datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc),
                },
            ],
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc),
            threshold_mins=3,
        )
        # a: on time, b: no data, c: 7 min late
        a = [x for x in result["attendee_costs"] if x["email"] == "a@co.com"][0]
        b = [x for x in result["attendee_costs"] if x["email"] == "b@co.com"][0]
        c = [x for x in result["attendee_costs"] if x["email"] == "c@co.com"][0]

        assert a["lateMins"] == 0.0
        assert b["lateMins"] == 0.0
        assert c["lateMins"] == 7.0
        assert c["selfCost"] > 0.0

    def test_negative_duration_treated_as_zero(self):
        """End before start = zero base cost."""
        result = calculate_meeting_cost(
            attendees=[{"email": "a@co.com", "rate": 100.0}],
            scheduled_start=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            threshold_mins=3,
        )
        assert result["total_cost"] == 0.0

    def test_join_at_none_explicitly(self):
        """joined_at explicitly set to None."""
        result = calculate_meeting_cost(
            attendees=[{"email": "a@co.com", "rate": 100.0, "joined_at": None}],
            scheduled_start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
            threshold_mins=3,
        )
        assert result["attendee_costs"][0]["lateMins"] == 0.0
        assert result["attendee_costs"][0]["joinedAt"] is None
