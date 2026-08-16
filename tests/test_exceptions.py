"""Tests for the typed exception hierarchy.

Covers:
- Inheritance graph (every typed exception descends from `SpondError`).
- Backward compatibility: `*NotFoundError` is still a `KeyError`,
  `SpondAPIError` is still a `ValueError`, and `AuthenticationError`
  is still importable from `spond` top-level.
- Raise sites use the typed forms (`get_event` raises `EventNotFoundError`,
  `get_person` raises `PersonNotFoundError`, `get_posts` HTTP failure
  raises `SpondAPIError`).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from spond import (
    AuthenticationError,
    ChatNotFoundError,
    EventNotFoundError,
    GroupNotFoundError,
    PersonNotFoundError,
    SpondAPIError,
    SpondError,
    SpondNotFoundError,
)
from spond.spond import Spond

from .conftest import MOCK_PASSWORD, MOCK_USERNAME


class TestExceptionHierarchy:
    """The hierarchy must be coherent: catching the base catches everything."""

    def test_all_descend_from_spond_error(self) -> None:
        for cls in (
            AuthenticationError,
            SpondAPIError,
            SpondNotFoundError,
            EventNotFoundError,
            GroupNotFoundError,
            PersonNotFoundError,
            ChatNotFoundError,
        ):
            assert issubclass(cls, SpondError), (
                f"{cls.__name__} must descend from SpondError"
            )

    def test_not_found_exceptions_are_keyerror(self) -> None:
        """Pre-OO callers wrote `except KeyError:` — the typed forms must
        remain compatible with that pattern."""
        for cls in (
            EventNotFoundError,
            GroupNotFoundError,
            PersonNotFoundError,
            ChatNotFoundError,
            SpondNotFoundError,
        ):
            assert issubclass(cls, KeyError), (
                f"{cls.__name__} must inherit from KeyError"
            )

    def test_api_error_is_valueerror(self) -> None:
        """Pre-OO callers wrote `except ValueError:` for HTTP failures —
        `SpondAPIError` must remain compatible."""
        assert issubclass(SpondAPIError, ValueError)

    def test_api_error_carries_status_body_url(self) -> None:
        exc = SpondAPIError(401, "Unauthorized", "https://api.spond.com/test")
        assert exc.status == 401
        assert exc.body == "Unauthorized"
        assert exc.url == "https://api.spond.com/test"
        # And the legacy message shape is preserved for substring-matchers
        assert "401" in str(exc)
        assert "Unauthorized" in str(exc)

    def test_api_error_truncates_long_body(self) -> None:
        long_body = "x" * 10000
        exc = SpondAPIError(500, long_body)
        # body attr keeps the full string, but the str() form is bounded
        assert exc.body == long_body
        assert len(str(exc)) < 1500

    def test_authentication_error_still_top_level_importable(self) -> None:
        """Pre-OO callers do `from spond import AuthenticationError` — that
        import path must keep working through the v1.x deprecation cycle."""
        # Already imported at module level; just assert it's the same class
        from spond.exceptions import AuthenticationError as AE2

        assert AuthenticationError is AE2


class TestRaiseSitesUseTypedExceptions:
    """Verify the production raise sites use the typed forms, not bare
    stdlib classes."""

    @pytest.mark.asyncio
    async def test_get_event_raises_event_not_found(self, mock_token) -> None:
        from spond.event import Event

        from .conftest import _MIN_EVENT_PAYLOAD

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        # Non-empty cache so the re-fetch doesn't fire; just no match.
        s.events = [Event.model_validate(_MIN_EVENT_PAYLOAD)]

        with pytest.raises(EventNotFoundError):
            await s.get_event("NOSUCHID")

    @pytest.mark.asyncio
    async def test_get_event_caught_by_keyerror(self, mock_token) -> None:
        """Backward compat: `except KeyError:` still works for `get_event`."""
        from spond.event import Event

        from .conftest import _MIN_EVENT_PAYLOAD

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.events = [Event.model_validate(_MIN_EVENT_PAYLOAD)]

        with pytest.raises(KeyError):
            await s.get_event("NOSUCHID")

    @pytest.mark.asyncio
    async def test_get_group_raises_group_not_found(self, mock_token) -> None:
        from spond.group import Group

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.groups = [Group.model_validate({"id": "EXISTS"})]

        with pytest.raises(GroupNotFoundError):
            await s.get_group("NOSUCHID")

    @pytest.mark.asyncio
    async def test_get_person_raises_person_not_found(self, mock_token) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.groups = []
        s.get_groups = AsyncMock(return_value=None)

        with pytest.raises(PersonNotFoundError):
            await s.get_person("anyone")

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_http_failure_raises_spond_api_error(
        self, mock_get, mock_token
    ) -> None:
        """`get_posts` HTTP failure path now raises `SpondAPIError`.
        Verify both the typed form and the legacy `ValueError` catch path."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_get.return_value.__aenter__.return_value.ok = False
        mock_get.return_value.__aenter__.return_value.status = 503
        mock_get.return_value.__aenter__.return_value.text = AsyncMock(
            return_value="Service Unavailable"
        )

        with pytest.raises(SpondAPIError) as exc_info:
            await s.get_posts()

        assert exc_info.value.status == 503
        assert "Service Unavailable" in exc_info.value.body

        # And the legacy `except ValueError:` shape still works
        mock_get.return_value.__aenter__.return_value.text = AsyncMock(
            return_value="Service Unavailable"
        )
        with pytest.raises(ValueError):  # noqa: PT011 — testing inheritance
            await s.get_posts()
