"""Tests for the ActiveRecord write surface: `Event.save()` and
`Event.delete()`.

`save()` is the universal create-or-update operation: dispatches on
`self.uid` presence (empty → POST `/sponds/` to create; set → POST
`/sponds/{uid}` via the existing `update()` machinery). On create it
mutates `self` in place with the persisted state from Spond and binds
the client.

`delete()` issues DELETE `/sponds/{uid}` and prunes the event from the
client's `events` cache so subsequent `get_event(uid)` lookups raise
`EventNotFoundError`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from spond import EventNotFoundError, SpondAPIError
from spond.event import Event
from spond.spond import Spond

from .conftest import _MIN_EVENT_PAYLOAD, MOCK_PASSWORD, MOCK_USERNAME


def _fresh_event() -> Event:
    """Build an unsaved Event (no uid) suitable for the create path."""
    return Event(
        uid="",
        heading="New Event",
        start_time=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 6, 1, 11, 0, tzinfo=UTC),
        type="EVENT",
        owners=[{"id": "PROFILE1", "response": "accepted"}],
        recipients={"group": {"id": "GROUP1"}},
    )


class TestSaveCreate:
    """Create path: `event.save()` on an instance with no uid."""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_create_populates_uid_in_place(self, mock_post) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        event = _fresh_event()

        # Spond returns the created event with a fresh uid + server-managed
        # fields populated.
        api_response = {
            **_MIN_EVENT_PAYLOAD,
            "id": "NEWUID",
            "heading": "New Event",
            "creatorId": "PROFILE1",
            "createdTime": "2026-05-14T20:00:00Z",
        }
        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=api_response
        )

        result = await event.save(client=s)

        # save() returns self (mutated in place), not a fresh instance.
        assert result is event
        assert event.uid == "NEWUID"
        # Server-managed fields applied to self
        assert event.creator_uid == "PROFILE1"
        # Client bound for subsequent operations
        assert event._client is s

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_create_posts_to_collection_url(self, mock_post) -> None:
        """The create path POSTs to `/sponds/` (no uid in path)."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        event = _fresh_event()

        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={**_MIN_EVENT_PAYLOAD, "id": "NEWUID"}
        )

        await event.save(client=s)

        called_url = mock_post.call_args[0][0]
        assert called_url.endswith("/sponds/"), (
            f"create should POST to /sponds/ (collection), got {called_url}"
        )

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_create_includes_recipients_in_payload(self, mock_post) -> None:
        """`recipients` is required for create (and was previously being
        stripped by `_EVENT_READ_ONLY_FIELDS`). Locks in the fix."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        event = _fresh_event()

        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={**_MIN_EVENT_PAYLOAD, "id": "NEWUID"}
        )

        await event.save(client=s)

        posted = mock_post.call_args[1]["json"]
        assert "recipients" in posted, (
            "create payload must include recipients — Spond requires it"
        )
        assert posted["recipients"] == {"group": {"id": "GROUP1"}}

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_create_appends_to_client_cache(self, mock_post) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        s.events = []  # empty list, not None — so we observe the append
        event = _fresh_event()

        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={**_MIN_EVENT_PAYLOAD, "id": "NEWUID"}
        )

        await event.save(client=s)

        assert len(s.events) == 1
        assert s.events[0].uid == "NEWUID"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_create_initialises_empty_cache(self, mock_post) -> None:
        """When `s.events is None` (never fetched), create initialises the
        cache rather than no-oping."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        s.events = None
        event = _fresh_event()

        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={**_MIN_EVENT_PAYLOAD, "id": "NEWUID"}
        )

        await event.save(client=s)

        assert s.events is not None
        assert len(s.events) == 1

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_create_raises_on_http_error(self, mock_post) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        event = _fresh_event()

        mock_post.return_value.__aenter__.return_value.ok = False
        mock_post.return_value.__aenter__.return_value.status = 500
        mock_post.return_value.__aenter__.return_value.text = AsyncMock(
            return_value="Server Error"
        )

        with pytest.raises(SpondAPIError) as exc_info:
            await event.save(client=s)
        assert exc_info.value.status == 500

    @pytest.mark.asyncio
    async def test_save_without_client_raises(self) -> None:
        """Calling `save()` on an unbound new instance without passing
        `client=` must raise — there's no way to send the POST."""
        event = _fresh_event()
        with pytest.raises(RuntimeError, match="no client bound"):
            await event.save()


class TestSaveUpdate:
    """Update path: `event.save()` on an instance with an existing uid."""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_existing_posts_to_uid_url(self, mock_post) -> None:
        """A saved Event saves to `/sponds/{uid}` (delegates to `update()`)."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)

        api_response = {**_MIN_EVENT_PAYLOAD, "heading": "Renamed"}
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=api_response
        )

        event.heading = "Renamed"
        await event.save()

        called_url = mock_post.call_args[0][0]
        assert called_url.endswith(f"/sponds/{event.uid}"), (
            f"update should POST to /sponds/{event.uid}, got {called_url}"
        )
        assert event.heading == "Renamed"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_existing_uses_bound_client(self, mock_post) -> None:
        """Subsequent saves don't need a `client` argument."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)

        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=_MIN_EVENT_PAYLOAD
        )

        # No client kwarg — should use event._client which from_api wired.
        await event.save()
        mock_post.assert_called_once()


class TestDelete:
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.delete")
    async def test_delete_issues_delete_request(self, mock_delete) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)
        s.events = [event]

        mock_delete.return_value.__aenter__.return_value.ok = True
        mock_delete.return_value.__aenter__.return_value.status = 200

        await event.delete()

        called_url = mock_delete.call_args[0][0]
        assert called_url.endswith(f"/sponds/{event.uid}"), (
            f"delete should DELETE /sponds/{event.uid}, got {called_url}"
        )

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.delete")
    async def test_delete_prunes_from_client_cache(self, mock_delete) -> None:
        """After delete, the event must no longer be in `client.events` so
        a subsequent `get_event(uid)` raises `EventNotFoundError`."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        # Cache has two events — one we'll delete, one we won't
        e1 = Event.from_api({**_MIN_EVENT_PAYLOAD, "id": "TODELETE"}, s)
        e2 = Event.from_api({**_MIN_EVENT_PAYLOAD, "id": "KEEP"}, s)
        s.events = [e1, e2]

        mock_delete.return_value.__aenter__.return_value.ok = True

        await e1.delete()

        # e1 gone from cache; e2 stays
        assert len(s.events) == 1
        assert s.events[0].uid == "KEEP"

        # And get_event(deleted_uid) raises
        with pytest.raises(EventNotFoundError):
            await s.get_event("TODELETE")

    @pytest.mark.asyncio
    async def test_delete_without_client_raises(self) -> None:
        event = Event.model_validate(_MIN_EVENT_PAYLOAD)
        # No client wired (didn't go through from_api)
        with pytest.raises(RuntimeError, match="no client"):
            await event.delete()

    @pytest.mark.asyncio
    async def test_delete_without_uid_raises(self) -> None:
        """Cannot delete an event that was never persisted (no uid)."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        event = _fresh_event()
        event._client = s  # bound but unsaved

        with pytest.raises(RuntimeError, match="unsaved"):
            await event.delete()

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.delete")
    async def test_delete_raises_on_http_error(self, mock_delete) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)

        mock_delete.return_value.__aenter__.return_value.ok = False
        mock_delete.return_value.__aenter__.return_value.status = 403
        mock_delete.return_value.__aenter__.return_value.text = AsyncMock(
            return_value="Forbidden"
        )

        with pytest.raises(SpondAPIError) as exc_info:
            await event.delete()
        assert exc_info.value.status == 403


class TestSaveRoundtrip:
    """Combined save/delete roundtrip — the canonical ActiveRecord flow."""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.delete")
    @patch("aiohttp.ClientSession.post")
    async def test_create_then_save_then_delete(self, mock_post, mock_delete) -> None:
        """Construct → save (create) → mutate → save (update) → delete.
        The canonical ActiveRecord lifecycle, end to end."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        s.events = []
        event = _fresh_event()

        # Create: returns with uid
        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={**_MIN_EVENT_PAYLOAD, "id": "C1", "heading": "New Event"}
        )

        await event.save(client=s)
        assert event.uid == "C1"

        # Update: mutate + save
        event.heading = "Renamed"
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={**_MIN_EVENT_PAYLOAD, "id": "C1", "heading": "Renamed"}
        )
        await event.save()
        assert event.heading == "Renamed"

        # Delete
        mock_delete.return_value.__aenter__.return_value.ok = True
        await event.delete()
        assert event.uid not in {e.uid for e in s.events}
