"""Tests for authentication — `_extract_access_token` parsing, login flow,
and the `require_authentication` decorator's metadata preservation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from spond import AuthenticationError
from spond.base import _SpondBase
from spond.spond import Spond

from .conftest import MOCK_PASSWORD, MOCK_USERNAME


class TestLogin:
    @pytest.mark.parametrize(
        ("login_result", "expected"),
        [
            (
                {"accessToken": {"token": "ABC", "expiration": "2026-05-14T12:00:00Z"}},
                "ABC",
            ),
        ],
    )
    def test_extract_access_token__happy_path(self, login_result, expected) -> None:
        assert _SpondBase._extract_access_token(login_result) == expected

    @pytest.mark.parametrize(
        "login_result",
        [
            {"error": "Invalid credentials"},
            {"accessToken": None},
            {"accessToken": {}},
            {"accessToken": {"token": ""}},
            {"accessToken": {"token": None}},
        ],
    )
    def test_extract_access_token__bad_shape_raises(self, login_result) -> None:
        with pytest.raises(AuthenticationError):
            _SpondBase._extract_access_token(login_result)

    def test_extract_access_token__error_message_drops_sensitive_fields(
        self,
    ) -> None:
        """The exception message must not leak unwhitelisted fields from the
        login response (e.g. a 2FA challenge `token` or `phoneNumber`)."""
        login_result = {
            "token": "TWO_FA_CHALLENGE_TOKEN_VALUE",
            "phoneNumber": "****12",
            "errorKey": "twoFactorRequired",
        }
        with pytest.raises(AuthenticationError) as exc_info:
            _SpondBase._extract_access_token(login_result)

        message = str(exc_info.value)
        assert "TWO_FA_CHALLENGE_TOKEN_VALUE" not in message
        assert "phoneNumber" not in message
        assert "twoFactorRequired" in message  # whitelisted field surfaces

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_login__happy_path(self, mock_post) -> None:
        mock_response = {
            "accessToken": {"token": "ABC", "expiration": "2026-05-14T12:00:00Z"},
            "refreshToken": {"token": "REF", "expiration": "2026-08-11T12:00:00Z"},
            "passwordToken": {"token": "PWD", "expiration": "2026-05-13T13:00:00Z"},
        }
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=mock_response
        )

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        await s.login()

        mock_post.assert_called_once_with(
            "https://api.spond.com/core/v1/auth2/login",
            json={"email": MOCK_USERNAME, "password": MOCK_PASSWORD},
        )
        assert s.token == "ABC"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_login__error_response_raises(self, mock_post) -> None:
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={"error": "Invalid credentials"}
        )

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        with pytest.raises(AuthenticationError):
            await s.login()
        assert s.token is None


class TestRequireAuthenticationDecorator:
    """The `require_authentication` decorator must preserve the wrapped
    method's metadata (signature, docstring, name) so `inspect`-based
    tools — pdoc, IDE help, tab completion — see the real method
    rather than the wrapper's `(*args, **kwargs)` shim.
    """

    def test_decorator_preserves_signature(self) -> None:
        """Decorated methods must expose their real parameter list."""
        import inspect

        # `get_posts` is decorated and has a distinctive signature
        params = list(inspect.signature(Spond.get_posts).parameters)
        assert params == ["self", "group_id", "max_posts", "include_comments"]

    def test_decorator_preserves_docstring(self) -> None:
        """Decorated methods must expose their own docstring, not the
        wrapper's."""
        import inspect

        doc = inspect.getdoc(Spond.get_profile) or ""
        # Wrapper docstring would start with 'Decorator that...' if leaked.
        assert "Retrieve the authenticated user's profile." in doc

    def test_decorator_preserves_name(self) -> None:
        """`__name__` must be the method's, not 'wrapper'."""
        assert Spond.get_events.__name__ == "get_events"
