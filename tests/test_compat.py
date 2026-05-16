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

        mock_post.return_value.__aenter__.return_value.ok = True
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

        mock_post.return_value.__aenter__.return_value.ok = True
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

    def test_contains_non_string_key_returns_false(self) -> None:
        """`__contains__` with a non-string key must return False without
        raising — dict-compat callers may inadvertently pass ints."""
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        assert 42 not in e
        assert None not in e

    def test_keys_returns_api_shaped_list(self) -> None:
        """`DictCompatModel.keys()` yields API-alias names for fields that
        were populated from source data, matching `.keys()` on a raw dict."""
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        k = e.keys()
        assert isinstance(k, list)
        assert "id" in k  # alias, not "uid"
        assert "heading" in k
        assert "startTimestamp" in k  # alias, not "start_time"
        assert "description" not in k  # absent from _MIN_EVENT_PAYLOAD

    def test_values_returns_values_for_set_fields(self) -> None:
        """`DictCompatModel.values()` returns the values for fields present
        in the source payload, in field-declaration order."""
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        vals = e.values()
        assert isinstance(vals, list)
        # "ID1" must be among the values (it's `uid`, present in source)
        assert "ID1" in vals
        assert "Event One" in vals  # heading

    def test_items_returns_key_value_pairs(self) -> None:
        """`DictCompatModel.items()` returns `(api_key, value)` tuples for
        every field present in the source data, mirroring dict.items()."""
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        items = dict(e.items())
        assert items["id"] == "ID1"
        assert items["heading"] == "Event One"
        assert "description" not in items  # not in source

    def test_items_includes_extra_fields(self) -> None:
        """Extra (unmodelled) fields surface in `.items()` with their
        original key names."""
        payload = {**_MIN_EVENT_PAYLOAD, "customExtra": "hello"}
        e = Event.model_validate(payload)
        items = dict(e.items())
        assert items["customExtra"] == "hello"


class TestLenientDate:
    """Unit tests for the `_parse_date_lenient` validator used by
    `LenientDate` fields on `Member` and `Profile`."""

    def test_none_passes_through(self) -> None:
        from spond._compat import _parse_date_lenient

        assert _parse_date_lenient(None) is None

    def test_date_object_passes_through(self) -> None:
        from datetime import date

        from spond._compat import _parse_date_lenient

        d = date(2000, 6, 15)
        assert _parse_date_lenient(d) is d

    def test_valid_iso_string_parsed(self) -> None:
        from datetime import date

        from spond._compat import _parse_date_lenient

        result = _parse_date_lenient("1995-03-22")
        assert result == date(1995, 3, 22)

    def test_invalid_date_string_returns_none(self) -> None:
        """Malformed dates (e.g. impossible day) must not raise — return None."""
        from spond._compat import _parse_date_lenient

        assert _parse_date_lenient("2012-03-99") is None
        assert _parse_date_lenient("not-a-date") is None

    def test_non_string_non_date_returns_none(self) -> None:
        """Non-string, non-date values (e.g. an int) must return None rather
        than raising TypeError."""
        from spond._compat import _parse_date_lenient

        assert _parse_date_lenient(20001231) is None
        assert _parse_date_lenient([]) is None

    def test_lenient_date_field_on_member(self) -> None:
        """A malformed `dateOfBirth` in a Member payload must not crash
        validation — the field silently becomes None."""
        from spond.person import Member

        m = Member.model_validate({"id": "M1", "dateOfBirth": "2012-03-99"})
        assert m.date_of_birth is None

    def test_lenient_date_field_on_profile(self) -> None:
        """Same resilience on Profile.date_of_birth."""
        from spond.profile import Profile

        p = Profile.model_validate({"id": "P1", "dateOfBirth": "invalid"})
        assert p.date_of_birth is None
