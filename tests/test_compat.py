"""Tests for the `DictCompatModel` shim — the bridge that lets pre-OO
callers keep using dict-style subscript/`.get()`/`in`/`len()`/`iter()`
against typed Pydantic models while emitting `DeprecationWarning`s.

Also covers `extra="allow"` forward-compat behaviour and a couple of
Event-update-payload regression guards (which exercise the same
shim machinery via `model_dump(exclude_unset=True, exclude_none=True)`)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from spond.event import Event
from spond.group import Group
from spond.spond import Spond

from .conftest import _MIN_EVENT_PAYLOAD, MOCK_PASSWORD, MOCK_USERNAME


class TestDictCompat:
    """The DictCompatModel shim makes typed models behave like the dicts they
    replaced, with a DeprecationWarning on subscript and `.get()`."""

    def test_subscript_via_alias_warns_and_returns_value(self) -> None:
        import warnings as _w

        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        with _w.catch_warnings(record=True) as caught:
            _w.simplefilter("always")
            value = e["id"]  # API alias
        assert value == "ID1"
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)

    def test_subscript_via_python_name_warns_and_returns_value(self) -> None:
        import warnings as _w

        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        with _w.catch_warnings(record=True) as caught:
            _w.simplefilter("always")
            value = e["heading"]
        assert value == "Event One"
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)

    def test_subscript_missing_key_raises_keyerror(self) -> None:
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        with pytest.raises(KeyError):
            _ = e["does_not_exist"]

    def test_get_with_default_returns_default_for_missing_key(self) -> None:
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        sentinel = object()
        assert e.get("does_not_exist", sentinel) is sentinel

    def test_contains_works_for_alias_and_python_name(self) -> None:
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        assert "id" in e  # alias
        assert "heading" in e  # python name
        assert "startTimestamp" in e  # alias
        assert "start_time" in e  # python name
        assert "does_not_exist" not in e

    def test_iter_yields_api_shaped_keys(self) -> None:
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        keys = list(e)
        assert "id" in keys  # alias, not "uid"
        assert "startTimestamp" in keys  # alias, not "start_time"

    def test_len_contains_and_iter_agree(self) -> None:
        """`__len__`, `__contains__`, and `__iter__` must all reflect the
        same view of "what's actually in this object" — pre-OO callers
        relied on dict semantics where these three are always consistent."""
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        keys = list(e)
        assert len(e) == len(keys)
        for k in keys:
            assert k in e
        # A field with a default that wasn't in the source data must NOT
        # appear in any of the three views.
        assert "description" not in e  # not in _MIN_EVENT_PAYLOAD
        assert "description" not in keys

    def test_extra_allow_preserves_unmodelled_fields(self) -> None:
        """With `model_config = extra="allow"`, Spond-side fields the SDK
        doesn't model are preserved on the instance and accessible via the
        dict-compat shim (with deprecation warning)."""
        import warnings as _w

        payload = {**_MIN_EVENT_PAYLOAD, "futureSpondField": "preserved"}
        e = Event.model_validate(payload)
        # Iteration includes the extra
        assert "futureSpondField" in e
        assert "futureSpondField" in list(e)
        with _w.catch_warnings(record=True) as caught:
            _w.simplefilter("always")
            value = e["futureSpondField"]
        assert value == "preserved"
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)

    def test_models_survive_missing_optional_fields(self) -> None:
        """A previously-required field dropping to a default must not crash
        the typed model. Locks in the resilience relaxation done after
        rounds of review feedback."""
        from spond.person import Member
        from spond.post import Post
        from spond.profile import Profile

        # Member with no name fields — used to crash, now defaults to ""
        m = Member.model_validate({"id": "M1"})
        assert m.first_name == ""
        assert m.last_name == ""
        # Post without timestamp — used to crash, now None
        p = Post.model_validate({"id": "P1"})
        assert p.timestamp is None
        # __str__ must not raise even though timestamp is None — guards the
        # AttributeError that resilience relaxation otherwise re-introduced.
        assert "?" in str(p)
        # Profile with no name fields — same relaxation
        pr = Profile.model_validate({"id": "PR1"})
        assert pr.first_name == ""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_event_update_excludes_unset_default_collections(
        self, mock_post, mock_token
    ) -> None:
        """`Event.update()` must NOT send empty-list defaults for fields
        the source API didn't include (e.g. `owners=[]`, `attachments=[]`).
        Spond could interpret an explicit empty list as 'clear all
        owners', overwriting concurrent server-side changes.
        Regression guard for the `exclude_unset=True` fix."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        # _MIN_EVENT_PAYLOAD doesn't include `owners` or `attachments`, so
        # the Event has them at their default ([]). They must NOT round-trip.
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)
        assert event.owners == []
        assert event.attachments == []

        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=_MIN_EVENT_PAYLOAD
        )
        await event.update(heading="Renamed")

        posted = mock_post.call_args[1]["json"]
        # The caller's update was applied
        assert posted["heading"] == "Renamed"
        # Empty-list defaults were NOT sent (because they weren't in the source)
        assert "owners" not in posted
        assert "attachments" not in posted

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_event_update_excludes_none_fields(
        self, mock_post, mock_token
    ) -> None:
        """`Event.update()` must NOT send `null` for optional fields that
        Spond didn't populate — Spond could interpret `null` as 'clear this
        field' rather than 'leave unchanged'."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        # _MIN_EVENT_PAYLOAD has no `description`, so Event.description=None.
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)
        assert event.description is None

        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=_MIN_EVENT_PAYLOAD
        )
        await event.update(heading="Renamed")

        # The POST payload must contain `heading` (caller updated it) but
        # NOT `description` (it was None and shouldn't be cleared).
        posted = mock_post.call_args[1]["json"]
        assert posted["heading"] == "Renamed"
        assert "description" not in posted

    def test_extra_allow_on_profile_and_group(self) -> None:
        """`extra="allow"` must work uniformly across top-level types, not
        just Event — this is the forward-compat invariant for the whole
        public surface."""
        from spond.profile import Profile

        p = Profile.model_validate(
            {"id": "P1", "firstName": "A", "lastName": "B", "newSpondField": 42}
        )
        assert "newSpondField" in p
        # `__pydantic_extra__` is the portable accessor for `extra="allow"`
        # extras — native attribute access (`p.newSpondField`) works on
        # current Pydantic 2.x but behaviour varies subtly across minor
        # versions for camelCase keys, so this is the version-stable form.
        assert p.__pydantic_extra__["newSpondField"] == 42

        g = Group.model_validate({"id": "G1", "name": "GG", "newGroupAttr": ["x"]})
        assert "newGroupAttr" in g
        assert g.__pydantic_extra__["newGroupAttr"] == ["x"]
