"""Tests for the async member-resolution helpers on `Event`:
`accepted_members()`, `declined_members()`, `unanswered_members()`,
`waiting_list_members()`, `unconfirmed_members()`.

Each resolves the corresponding `responses.*_uids` list to typed
`Member`/`Guardian` objects via the client's group cache, fetching it
lazily if empty. UIDs that no longer correspond to a current group
member are silently dropped (left members aren't an error).
"""

from __future__ import annotations

import pytest

from spond.event import Event
from spond.group import Group
from spond.person import Guardian, Member
from spond.spond import Spond

from .conftest import _MIN_EVENT_PAYLOAD, MOCK_PASSWORD, MOCK_USERNAME


def _spond_with_group() -> Spond:
    """Build a Spond client with one group containing three members and
    one guardian, all pre-cached so no HTTP fires."""
    s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
    s.token = "MOCK_TOKEN"
    s.groups = [
        Group.from_api(
            {
                "id": "GID1",
                "name": "G",
                "members": [
                    {
                        "id": "M1",
                        "firstName": "Alice",
                        "lastName": "A",
                        "guardians": [
                            {"id": "G1", "firstName": "Pat", "lastName": "A"}
                        ],
                    },
                    {"id": "M2", "firstName": "Bob", "lastName": "B"},
                    {"id": "M3", "firstName": "Charlie", "lastName": "C"},
                ],
            },
            s,
        )
    ]
    return s


def _event_with_responses(
    accepted: list[str] | None = None,
    declined: list[str] | None = None,
    unanswered: list[str] | None = None,
    waiting_list: list[str] | None = None,
    unconfirmed: list[str] | None = None,
) -> Event:
    return Event.model_validate(
        {
            **_MIN_EVENT_PAYLOAD,
            "responses": {
                "acceptedIds": accepted or [],
                "declinedIds": declined or [],
                "unansweredIds": unanswered or [],
                "waitinglistIds": waiting_list or [],
                "unconfirmedIds": unconfirmed or [],
            },
        }
    )


class TestAcceptedMembers:
    @pytest.mark.asyncio
    async def test_resolves_uids_to_typed_members(self) -> None:
        s = _spond_with_group()
        e = _event_with_responses(accepted=["M1", "M3"])
        e._client = s

        members = await e.accepted_members()

        assert len(members) == 2
        assert all(isinstance(m, Member) for m in members)
        uids = [m.uid for m in members]
        assert uids == ["M1", "M3"]  # preserves order from response list

    @pytest.mark.asyncio
    async def test_resolves_guardian_uids(self) -> None:
        """A uid that matches a guardian (not a member) returns the
        Guardian — same lookup index covers both."""
        s = _spond_with_group()
        e = _event_with_responses(accepted=["G1"])
        e._client = s

        members = await e.accepted_members()
        assert len(members) == 1
        assert isinstance(members[0], Guardian)
        assert members[0].uid == "G1"

    @pytest.mark.asyncio
    async def test_unknown_uids_are_silently_dropped(self) -> None:
        """A uid in the response list that no longer matches any group
        member (e.g. they left the group) is silently omitted — the rest
        still resolve."""
        s = _spond_with_group()
        e = _event_with_responses(accepted=["M1", "EXMEMBER", "M2"])
        e._client = s

        members = await e.accepted_members()
        assert [m.uid for m in members] == ["M1", "M2"]

    @pytest.mark.asyncio
    async def test_empty_accepted_list_returns_empty(self) -> None:
        s = _spond_with_group()
        e = _event_with_responses(accepted=[])
        e._client = s

        assert await e.accepted_members() == []

    @pytest.mark.asyncio
    async def test_no_client_raises_runtime_error(self) -> None:
        """An Event constructed without a client (e.g. via
        `model_validate(raw)`) can't fetch groups."""
        e = _event_with_responses(accepted=["M1"])
        # _client is None
        with pytest.raises(RuntimeError, match="no client attached"):
            await e.accepted_members()

    @pytest.mark.asyncio
    async def test_empty_groups_cache_returns_empty(self) -> None:
        """When the client has no groups at all (or `get_groups()` returns
        None), all helpers return an empty list rather than raising."""
        from unittest.mock import AsyncMock

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK_TOKEN"
        s.groups = None
        s.get_groups = AsyncMock(return_value=None)

        e = _event_with_responses(accepted=["ANY"])
        e._client = s

        assert await e.accepted_members() == []


class TestSiblingHelpers:
    """Verify the other four siblings route to their respective uid lists."""

    @pytest.mark.asyncio
    async def test_declined_members(self) -> None:
        s = _spond_with_group()
        e = _event_with_responses(declined=["M2"])
        e._client = s

        members = await e.declined_members()
        assert [m.uid for m in members] == ["M2"]

    @pytest.mark.asyncio
    async def test_unanswered_members(self) -> None:
        s = _spond_with_group()
        e = _event_with_responses(unanswered=["M3", "M1"])
        e._client = s

        members = await e.unanswered_members()
        assert [m.uid for m in members] == ["M3", "M1"]

    @pytest.mark.asyncio
    async def test_waiting_list_members(self) -> None:
        s = _spond_with_group()
        e = _event_with_responses(waiting_list=["M2"])
        e._client = s

        members = await e.waiting_list_members()
        assert [m.uid for m in members] == ["M2"]

    @pytest.mark.asyncio
    async def test_unconfirmed_members(self) -> None:
        s = _spond_with_group()
        e = _event_with_responses(unconfirmed=["G1"])
        e._client = s

        members = await e.unconfirmed_members()
        assert [m.uid for m in members] == ["G1"]
        assert isinstance(members[0], Guardian)
