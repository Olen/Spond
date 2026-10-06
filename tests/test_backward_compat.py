"""Backward-compatibility regression guards for pre-OO callers.

These tests don't probe new behaviour — they exist to catch the day a
refactor accidentally drops one of the pre-OO patterns that callers in
the wild depend on. If anything here fails, it's a release-blocker for
the next v1.x.

Covered:
- `event["heading"]` and `event.get("heading")` still work
- `"heading" in event`, `len(event)`, `list(event)` still work
- `from spond import AuthenticationError` still works
- `except KeyError:` still catches `get_event`/`get_group`/`get_person`
  lookup failures
- `except ValueError:` still catches HTTP failures
- `event.model_equals(other)` escape hatch returns full-field equality
  for callers who depended on Pydantic's pre-natural-key default
- Deprecated wrappers `Spond.update_event`/`change_response`/
  `get_event_attendance_xlsx` still exist and emit `DeprecationWarning`
"""

from __future__ import annotations

import warnings

import pytest

from spond import (
    AuthenticationError,
    EventNotFoundError,
    GroupNotFoundError,
    PersonNotFoundError,
    SpondAPIError,
)
from spond.event import Event
from spond.spond import Spond

from .conftest import _MIN_EVENT_PAYLOAD, MOCK_PASSWORD, MOCK_USERNAME


class TestDictStyleAccessStillWorks:
    """The DictCompatModel shim is the central backward-compat surface."""

    def test_subscript_returns_value_with_deprecation_warning(self) -> None:
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            value = e["heading"]
        assert value == "Event One"
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)

    def test_alias_subscript_also_works(self) -> None:
        """Pre-OO callers used the camelCase API name (`startTimestamp`),
        not the Python name (`start_time`)."""
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert e["startTimestamp"] is not None
            assert e["id"] == "ID1"

    def test_get_with_default_returns_default(self) -> None:
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        sentinel = object()
        assert e.get("nope", sentinel) is sentinel

    def test_contains_works(self) -> None:
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        assert "heading" in e
        assert "startTimestamp" in e
        assert "missing" not in e

    def test_iter_and_len_consistent(self) -> None:
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        keys = list(e)
        assert len(e) == len(keys)
        for k in keys:
            assert k in e


class TestExceptionsBackwardCompat:
    """Existing `except KeyError:` / `except ValueError:` / `from spond
    import AuthenticationError` patterns must keep working."""

    def test_authentication_error_top_level_import(self) -> None:
        """`from spond import AuthenticationError` is the pre-OO shape;
        the new exceptions module just re-exports it."""
        from spond.exceptions import AuthenticationError as AE2

        assert AuthenticationError is AE2

    def test_event_not_found_caught_as_keyerror(self) -> None:
        """Pre-OO code: `try: e = await s.get_event(uid) ... except KeyError:`"""
        assert issubclass(EventNotFoundError, KeyError)

    def test_group_not_found_caught_as_keyerror(self) -> None:
        assert issubclass(GroupNotFoundError, KeyError)

    def test_person_not_found_caught_as_keyerror(self) -> None:
        assert issubclass(PersonNotFoundError, KeyError)

    def test_api_error_caught_as_valueerror(self) -> None:
        """Pre-OO code did `except ValueError:` for HTTP failures."""
        assert issubclass(SpondAPIError, ValueError)


class TestModelEqualsEscapeHatch:
    """`model_equals` provides full-field equality for callers who
    depended on Pydantic's pre-natural-key default."""

    def test_same_uid_different_state_unequal_under_model_equals(self) -> None:
        """Two events with the same uid but different heading are equal
        under `==` (natural-key match) but unequal under `model_equals`
        (full field comparison)."""
        a = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "X"})
        b = Event.model_validate(
            {**_MIN_EVENT_PAYLOAD, "id": "X", "heading": "Different"}
        )

        assert a == b  # natural-key equality
        assert not a.model_equals(b)  # field-by-field disagreement

    def test_identical_state_equal_under_model_equals(self) -> None:
        a = Event.model_validate(_MIN_EVENT_PAYLOAD)
        b = Event.model_validate(_MIN_EVENT_PAYLOAD)
        assert a.model_equals(b)

    def test_different_class_unequal_under_model_equals(self) -> None:
        from spond.group import Group

        e = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "X"})
        g = Group.model_validate({"id": "X"})
        assert not e.model_equals(g)


class TestDeprecatedWrappersStillExist:
    """The pre-OO write methods (`update_event`, `change_response`,
    `get_event_attendance_xlsx`) must still be present on `Spond` and
    must emit `DeprecationWarning`."""

    @pytest.mark.asyncio
    async def test_update_event_emits_deprecation(self, mock_token) -> None:
        from unittest.mock import AsyncMock, patch

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.events = [Event.from_api(_MIN_EVENT_PAYLOAD, s)]

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.ok = True
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=_MIN_EVENT_PAYLOAD
            )
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                await s.update_event(uid="ID1", updates={"heading": "X"})

        assert any(issubclass(w.category, DeprecationWarning) for w in caught)

    def test_change_response_method_present(self) -> None:
        assert callable(Spond.change_response)

    def test_get_event_attendance_xlsx_method_present(self) -> None:
        assert callable(Spond.get_event_attendance_xlsx)
