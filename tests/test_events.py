"""Tests for Event surface — read APIs, deprecated wrappers, and the
ActiveRecord-style methods on the `Event` typed model (including the
`Match` subclass)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from spond.event import Event
from spond.spond import Spond

from .conftest import _MIN_EVENT_PAYLOAD, MOCK_PASSWORD, MOCK_TOKEN, MOCK_USERNAME


class TestEventMethods:
    @pytest.fixture
    def mock_events(self) -> list[Event]:
        """Two typed Event instances with placeholder data."""
        return [
            Event.model_validate(
                {**_MIN_EVENT_PAYLOAD, "id": "ID1", "heading": "Event One"}
            ),
            Event.model_validate(
                {**_MIN_EVENT_PAYLOAD, "id": "ID2", "heading": "Event Two"}
            ),
        ]

    @pytest.mark.asyncio
    async def test_get_event__happy_path(
        self, mock_events: list[Event], mock_token
    ) -> None:
        """Test that a valid `id` returns the matching event."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.events = mock_events
        s.token = mock_token
        g = await s.get_event("ID1")

        assert isinstance(g, Event)
        assert g.uid == "ID1"
        assert g.heading == "Event One"

    @pytest.mark.asyncio
    async def test_get_event__no_match_raises_exception(
        self, mock_events: list[Event], mock_token
    ) -> None:
        """Test that a non-matched `id` raises KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.events = mock_events
        s.token = mock_token

        with pytest.raises(KeyError):
            await s.get_event("ID3")

    @pytest.mark.asyncio
    async def test_get_event__blank_id_match_raises_exception(
        self, mock_events: list[Event], mock_token
    ) -> None:
        """Test that a blank `id` raises KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.events = mock_events
        s.token = mock_token

        with pytest.raises(KeyError):
            await s.get_event("")

    @pytest.mark.asyncio
    async def test_get_event__no_events_available_raises_keyerror(
        self, mock_token
    ) -> None:
        """`get_events()` is documented to return None when no events exist;
        `get_event()` should surface this as KeyError, not TypeError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.events = None
        s.get_events = AsyncMock()  # leaves self.events as None

        with pytest.raises(KeyError):
            await s.get_event("ID1")

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_update_event__returns_api_response(
        self, mock_post, mock_token
    ) -> None:
        """Deprecated `Spond.update_event()` should still return the POST response
        as a dict for backward compatibility (delegates to `Event.update()`)."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.events = [Event.from_api(_MIN_EVENT_PAYLOAD, s)]

        api_response = {**_MIN_EVENT_PAYLOAD, "heading": "New"}
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=api_response
        )

        import warnings as _warnings

        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            result = await s.update_event(uid="ID1", updates={"heading": "New"})

        # Deprecation warning fired
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
        # Result is a dict (model_dump output), with the updated heading
        assert isinstance(result, dict)
        assert result["heading"] == "New"
        # Regression guard for issue #239: the result must NOT be the
        # cached events list (the bug that was: `return self.events`).
        assert result is not s.events

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.put")
    async def test_change_response(self, mock_put, mock_payload, mock_token) -> None:
        """Deprecated `Spond.change_response()` should still PUT to the same URL
        and return the API response (delegates to `Event.change_response()`)."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.events = [Event.from_api(_MIN_EVENT_PAYLOAD, s)]

        mock_response_data = {
            "acceptedIds": ["PID1", "PID2"],
            "declinedIds": ["PID3"],
            "unansweredIds": [],
            "waitinglistIds": [],
            "unconfirmedIds": [],
            "declineMessages": {"PID3": "sick cannot make it"},
        }
        mock_put.return_value.__aenter__.return_value.status = 200
        mock_put.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=mock_response_data
        )

        import warnings as _warnings

        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            response = await s.change_response(
                uid="ID1", user="PID3", payload=mock_payload
            )

        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
        mock_url = "https://api.spond.com/core/v1/sponds/ID1/responses/PID3"
        # The wrapper forwards `payload` verbatim — same bytes that go on
        # the wire on the pre-OO code path.
        mock_put.assert_called_once_with(
            mock_url,
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {mock_token}",
            },
            json=mock_payload,
        )
        assert response == mock_response_data


class TestEventOOMethods:
    """ActiveRecord methods on Event."""

    def test_event_str_with_start_time(self) -> None:
        """`Event.__str__` includes uid, heading and ISO start_time."""
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        s = str(e)
        assert "ID1" in s
        assert "Event One" in s
        assert "2026-01-01" in s  # from startTimestamp

    def test_event_str_without_start_time(self) -> None:
        """`Event.__str__` uses '?' sentinel when start_time is None."""
        e = Event.model_validate({**_MIN_EVENT_PAYLOAD, "startTimestamp": None})
        s = str(e)
        assert "?" in s

    def test_event_url_property(self) -> None:
        """`Event.url` must return the canonical Spond web URL."""
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        assert e.url == "https://spond.com/client/sponds/ID1/"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_event_update_returns_new_event(self, mock_post, mock_token) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)

        api_response = {**_MIN_EVENT_PAYLOAD, "heading": "Updated"}
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=api_response
        )

        result = await event.update(heading="Updated")
        assert isinstance(result, Event)
        assert result.heading == "Updated"
        assert result is not event  # immutable: returns new

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_event_update_accepts_positional_dict(
        self, mock_post, mock_token
    ) -> None:
        """`event.update(updates_dict)` works for keys that would clash with
        reserved kwargs when passed via `**` (e.g. `self`, `cls`)."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)

        api_response = {**_MIN_EVENT_PAYLOAD, "heading": "New"}
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=api_response
        )

        # Use the positional dict form
        result = await event.update({"heading": "New", "selfish": "any"})
        assert result.heading == "New"
        # Unknown key "selfish" was passed through to the API payload
        posted = mock_post.call_args[1]["json"]
        assert posted["selfish"] == "any"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_event_update_refreshes_client_cache(
        self, mock_post, mock_token
    ) -> None:
        """After `event.update()`, the client's events cache must hold the
        new instance — not the stale pre-update one — so subsequent
        `spond.get_event(uid)` calls return current state."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        original = Event.from_api(_MIN_EVENT_PAYLOAD, s)
        s.events = [original]

        api_response = {**_MIN_EVENT_PAYLOAD, "heading": "Refreshed"}
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=api_response
        )

        result = await original.update(heading="Refreshed")
        # Cache must now point at the new instance (in-place replacement
        # preserves the list identity for callers holding `s.events`).
        assert s.events is not None
        assert s.events[0] is result
        assert s.events[0].heading == "Refreshed"
        assert s.events[0] is not original

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.put")
    async def test_event_change_response_accepts(self, mock_put, mock_token) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)

        mock_put.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={"acceptedIds": ["MID1"]}
        )
        result = await event.change_response("MID1", accepted=True)
        assert result == {"acceptedIds": ["MID1"]}
        call_args = mock_put.call_args
        assert call_args[0][0].endswith("/sponds/ID1/responses/MID1")
        assert call_args[1]["json"]["accepted"] == "true"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.put")
    async def test_event_change_response_declines_with_message(
        self, mock_put, mock_token
    ) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)

        mock_put.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={"declinedIds": ["MID1"]}
        )
        await event.change_response("MID1", accepted=False, decline_message="busy")
        sent = mock_put.call_args[1]["json"]
        assert sent["accepted"] == "false"
        assert sent["declineMessage"] == "busy"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_event_attendance_xlsx_returns_bytes(
        self, mock_get, mock_token
    ) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)

        mock_get.return_value.__aenter__.return_value.read = AsyncMock(
            return_value=b"PKxlsx-bytes"
        )
        data = await event.attendance_xlsx()
        assert data == b"PKxlsx-bytes"
        assert mock_get.call_args[0][0].endswith("/sponds/ID1/export")


class TestMatch:
    """Match (Event subclass) dispatch and field parsing."""

    _MATCH_PAYLOAD = {
        **_MIN_EVENT_PAYLOAD,
        "matchEvent": True,
        "matchInfo": {
            "teamName": "Home FC",
            "opponentName": "Away FC",
            "type": "HOME",
            "teamScore": 2,
            "opponentScore": 1,
            "scoresSet": True,
            "scoresFinal": True,
            "scoresSetEver": True,
            "scoresPublic": True,
        },
    }

    def test_dispatch_returns_match_when_match_event_true(self) -> None:
        """`Spond.get_events()` constructs `Match` (Event subclass) when the
        raw payload has `matchEvent=True`, plain `Event` otherwise."""
        from spond.match import Match, MatchInfo
        from spond.spond import _typed_event

        # _typed_event doesn't call methods on the client, so None is fine
        # for the dispatch + parsing assertions below.
        regular = _typed_event(_MIN_EVENT_PAYLOAD, None)
        m = _typed_event(self._MATCH_PAYLOAD, None)

        assert type(regular) is Event
        assert isinstance(m, Match)
        assert isinstance(m, Event)  # subclass relationship
        assert isinstance(m.match_info, MatchInfo)
        assert m.match_info.team_name == "Home FC"
        assert m.match_info.opponent_name == "Away FC"
        assert m.match_info.type == "HOME"
        assert m.match_info.team_score == 2
        assert m.match_info.opponent_score == 1
        assert m.match_info.scores_final is True
        assert m.match_info.scores_public is True

    def test_match_score_update_path_is_through_event_update(self) -> None:
        """Match inherits Event.update; the `match_info` field must be
        included in the POST payload (not in _EVENT_READ_ONLY_FIELDS), so
        callers can edit scores via `match.update(matchInfo={...})`."""
        from spond.event import _EVENT_READ_ONLY_FIELDS
        from spond.match import Match

        assert "match_info" not in _EVENT_READ_ONLY_FIELDS
        # And it really is a declared field on Match (vs an unmodelled
        # passthrough via extra="allow"):
        assert "match_info" in Match.model_fields

    def test_match_info_optional_for_resilience(self) -> None:
        """A future API variant emitting matchEvent=True without matchInfo
        (or a half-populated match record) must not crash construction."""
        from spond.match import Match
        from spond.spond import _typed_event

        bare = _typed_event({**_MIN_EVENT_PAYLOAD, "matchEvent": True}, None)
        assert isinstance(bare, Match)
        assert bare.match_info is None

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_match_update_preserves_match_type(
        self, mock_post, mock_token
    ) -> None:
        """`match.update(...)` must return a `Match` instance, not a plain
        `Event` — otherwise subclass identity is silently dropped and the
        cache replacement loop demotes the entry to a non-Match. Regression
        guard for the `type(self).from_api(...)` fix."""
        from spond.match import Match
        from spond.spond import _typed_event

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        original = _typed_event(self._MATCH_PAYLOAD, s)
        assert isinstance(original, Match)
        s.events = [original]

        response = {**self._MATCH_PAYLOAD, "heading": "Updated Match"}
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=response
        )

        result = await original.update(heading="Updated Match")
        assert isinstance(result, Match), f"Got {type(result).__name__}, expected Match"
        # And the cache entry got swapped to the new Match instance, not a demoted Event.
        assert isinstance(s.events[0], Match)
        assert s.events[0] is result


class TestGetEventsHTTP:
    """Tests for the `Spond.get_events()` HTTP-fetch path — query parameter
    construction, error surfacing, and cache management."""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_events_happy_path(self, mock_get) -> None:
        """Two events come back from the API as typed Event objects and are
        cached on `self.events`."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = MOCK_TOKEN

        raw = [
            {**_MIN_EVENT_PAYLOAD, "id": "E1", "heading": "First"},
            {**_MIN_EVENT_PAYLOAD, "id": "E2", "heading": "Second"},
        ]
        mock_get.return_value.__aenter__.return_value.ok = True
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=raw)

        events = await s.get_events()

        assert events is not None
        assert len(events) == 2
        assert all(isinstance(e, Event) for e in events)
        assert events[0].uid == "E1"
        assert events[1].heading == "Second"
        assert s.events is events  # cache identity

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_events_returns_none_when_api_returns_null(
        self, mock_get
    ) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = MOCK_TOKEN

        mock_get.return_value.__aenter__.return_value.ok = True
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=None)

        events = await s.get_events()
        assert events is None
        assert s.events is None

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_events_api_error_raises_valueerror(self, mock_get) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = MOCK_TOKEN

        mock_get.return_value.__aenter__.return_value.ok = False
        mock_get.return_value.__aenter__.return_value.status = 403
        mock_get.return_value.__aenter__.return_value.text = AsyncMock(
            return_value="Forbidden"
        )

        with pytest.raises(ValueError, match="403"):
            await s.get_events()

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_events_datetime_filters_in_params(self, mock_get) -> None:
        """Datetime filter args must be serialised to the `_DT_FORMAT` string
        and included as query parameters."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = MOCK_TOKEN

        mock_get.return_value.__aenter__.return_value.ok = True
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=[])

        min_start = datetime(2026, 1, 1, tzinfo=UTC)
        max_start = datetime(2026, 6, 30, tzinfo=UTC)
        await s.get_events(min_start=min_start, max_start=max_start)

        params = mock_get.call_args[1]["params"]
        assert "minStartTimestamp" in params
        assert "maxStartTimestamp" in params

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_events_include_hidden_param(self, mock_get) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = MOCK_TOKEN

        mock_get.return_value.__aenter__.return_value.ok = True
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=[])

        await s.get_events(include_hidden=True)

        params = mock_get.call_args[1]["params"]
        assert params.get("includeHidden") == "true"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_events_group_and_subgroup_params(self, mock_get) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = MOCK_TOKEN

        mock_get.return_value.__aenter__.return_value.ok = True
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=[])

        await s.get_events(group_id="GRP1", subgroup_id="SUB1")

        params = mock_get.call_args[1]["params"]
        assert params["groupId"] == "GRP1"
        assert params["subGroupId"] == "SUB1"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_events_min_end_max_end_params(self, mock_get, mock_token) -> None:
        """The `min_end` and `max_end` datetime args must also be serialised
        and sent as `minEndTimestamp` / `maxEndTimestamp` query parameters."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_get.return_value.__aenter__.return_value.ok = True
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=[])

        min_end = datetime(2026, 3, 1, tzinfo=UTC)
        max_end = datetime(2026, 12, 31, tzinfo=UTC)
        await s.get_events(min_end=min_end, max_end=max_end)

        params = mock_get.call_args[1]["params"]
        assert "minEndTimestamp" in params
        assert "maxEndTimestamp" in params

    @pytest.mark.asyncio
    async def test_get_entity_unsupported_type_raises_not_implemented(
        self, mock_token
    ) -> None:
        """Passing an unknown entity-type string to `_get_entity` must raise
        `NotImplementedError` rather than silently returning None."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        with pytest.raises(NotImplementedError, match="not supported"):
            await s._get_entity("banana", "UID1")


class TestGetProfile:
    """Tests for `Spond.get_profile()` — HTTP fetch and caching."""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_profile_happy_path(self, mock_get) -> None:
        """Profile is returned as a typed Profile object and cached on
        `self.profile`."""
        from spond.profile import Profile

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = MOCK_TOKEN

        raw = {
            "id": "PROF1",
            "firstName": "Ola",
            "lastName": "Thoresen",
            "primaryEmail": "ola@example.invalid",
        }
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=raw)

        profile = await s.get_profile()

        assert isinstance(profile, Profile)
        assert profile.uid == "PROF1"
        assert profile.first_name == "Ola"
        assert profile.full_name == "Ola Thoresen"
        assert s.profile is profile  # cache identity

    def test_profile_str(self) -> None:
        """`Profile.__str__` includes uid and full name."""
        from spond.profile import Profile

        p = Profile.model_validate(
            {"id": "P1", "firstName": "Jane", "lastName": "Doe"}
        )
        s = str(p)
        assert "P1" in s
        assert "Jane Doe" in s
