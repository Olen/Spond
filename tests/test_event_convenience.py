"""Tests for the synchronous convenience properties on `Event`:
`is_past`, `is_upcoming`, `duration`, `has_responded(uid)`,
`response_for(uid)`.

All five are pure-Python: no HTTP, no client required.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from spond.event import Event

from .conftest import _MIN_EVENT_PAYLOAD


def _event_at(start: datetime, end: datetime | None = None, **overrides) -> Event:
    """Build an Event with the given start/end and arbitrary overrides."""
    payload = {
        **_MIN_EVENT_PAYLOAD,
        "startTimestamp": start.isoformat(),
        "endTimestamp": (end or start + timedelta(hours=1)).isoformat(),
        **overrides,
    }
    return Event.model_validate(payload)


class TestIsPast:
    def test_event_ending_in_past_is_past(self) -> None:
        past_start = datetime.now(UTC) - timedelta(days=2)
        past_end = past_start + timedelta(hours=1)
        assert _event_at(past_start, past_end).is_past

    def test_event_ending_in_future_is_not_past(self) -> None:
        future_start = datetime.now(UTC) + timedelta(days=2)
        future_end = future_start + timedelta(hours=1)
        assert not _event_at(future_start, future_end).is_past

    def test_event_without_start_or_end_is_not_past(self) -> None:
        """A half-populated record (no start/end) is never "past" — we don't
        know when it happens, so we don't claim it's over."""
        e = Event.model_validate(
            {**_MIN_EVENT_PAYLOAD, "startTimestamp": None, "endTimestamp": None}
        )
        assert not e.is_past

    def test_event_with_only_start_time_uses_start(self) -> None:
        """If `end_time` is unset, `is_past` falls back to `start_time`."""
        past_start = datetime.now(UTC) - timedelta(days=2)
        e = Event.model_validate(
            {
                **_MIN_EVENT_PAYLOAD,
                "startTimestamp": past_start.isoformat(),
                "endTimestamp": None,
            }
        )
        assert e.is_past


class TestIsUpcoming:
    def test_future_event_is_upcoming(self) -> None:
        future = datetime.now(UTC) + timedelta(days=2)
        assert _event_at(future).is_upcoming

    def test_past_event_is_not_upcoming(self) -> None:
        past = datetime.now(UTC) - timedelta(days=2)
        assert not _event_at(past).is_upcoming

    def test_event_without_start_is_not_upcoming(self) -> None:
        """Symmetric with `is_past=False` for the no-time case — neither
        property fires when both start_time and end_time are None."""
        e = Event.model_validate(
            {**_MIN_EVENT_PAYLOAD, "startTimestamp": None, "endTimestamp": None}
        )
        assert not e.is_upcoming
        assert not e.is_past


class TestDuration:
    def test_duration_returns_timedelta(self) -> None:
        start = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
        end = datetime(2026, 6, 1, 11, 30, tzinfo=UTC)
        e = _event_at(start, end)
        assert e.duration == timedelta(hours=1, minutes=30)

    def test_duration_is_none_when_end_time_missing(self) -> None:
        start = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
        e = Event.model_validate(
            {
                **_MIN_EVENT_PAYLOAD,
                "startTimestamp": start.isoformat(),
                "endTimestamp": None,
            }
        )
        assert e.duration is None

    def test_duration_is_none_when_start_time_missing(self) -> None:
        end = datetime(2026, 6, 1, 11, 0, tzinfo=UTC)
        e = Event.model_validate(
            {
                **_MIN_EVENT_PAYLOAD,
                "startTimestamp": None,
                "endTimestamp": end.isoformat(),
            }
        )
        assert e.duration is None


class TestResponseFor:
    """`response_for(uid)` returns the bucket the uid lives in."""

    def _event_with_responses(self) -> Event:
        return Event.model_validate(
            {
                **_MIN_EVENT_PAYLOAD,
                "responses": {
                    "acceptedIds": ["A1", "A2"],
                    "declinedIds": ["D1"],
                    "unansweredIds": ["U1"],
                    "waitinglistIds": ["W1"],
                    "unconfirmedIds": ["X1"],
                },
            }
        )

    def test_accepted_uid_returns_accepted(self) -> None:
        e = self._event_with_responses()
        assert e.response_for("A1") == "accepted"
        assert e.response_for("A2") == "accepted"

    def test_declined_uid_returns_declined(self) -> None:
        assert self._event_with_responses().response_for("D1") == "declined"

    def test_unanswered_uid_returns_unanswered(self) -> None:
        assert self._event_with_responses().response_for("U1") == "unanswered"

    def test_waiting_list_uid_returns_waiting_list(self) -> None:
        assert self._event_with_responses().response_for("W1") == "waiting_list"

    def test_unconfirmed_uid_returns_unconfirmed(self) -> None:
        assert self._event_with_responses().response_for("X1") == "unconfirmed"

    def test_unknown_uid_returns_none(self) -> None:
        assert self._event_with_responses().response_for("NOPE") is None

    def test_no_responses_returns_none(self) -> None:
        """An event with default-empty responses returns None for any uid."""
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        assert e.response_for("ANYONE") is None


class TestHasResponded:
    """`has_responded(uid)` is True for any concrete response other than
    `unanswered`."""

    def _event_with_responses(self) -> Event:
        return Event.model_validate(
            {
                **_MIN_EVENT_PAYLOAD,
                "responses": {
                    "acceptedIds": ["A1"],
                    "declinedIds": ["D1"],
                    "unansweredIds": ["U1"],
                    "waitinglistIds": ["W1"],
                    "unconfirmedIds": ["X1"],
                },
            }
        )

    def test_accepted_has_responded(self) -> None:
        assert self._event_with_responses().has_responded("A1")

    def test_declined_has_responded(self) -> None:
        assert self._event_with_responses().has_responded("D1")

    def test_waiting_list_has_responded(self) -> None:
        assert self._event_with_responses().has_responded("W1")

    def test_unconfirmed_has_responded(self) -> None:
        """`unconfirmed` is still a concrete response — only `unanswered`
        means "no response given yet"."""
        assert self._event_with_responses().has_responded("X1")

    def test_unanswered_has_not_responded(self) -> None:
        """The whole point of the `unanswered` bucket: these uids haven't
        responded yet."""
        assert not self._event_with_responses().has_responded("U1")

    def test_unknown_uid_has_not_responded(self) -> None:
        """An uid not invited to the event returns False — not a typed
        record of non-response, but also not a positive response."""
        assert not self._event_with_responses().has_responded("NOPE")
