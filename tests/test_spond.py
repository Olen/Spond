"""Test suite for Spond class."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from spond import AuthenticationError
from spond.base import _SpondBase
from spond.spond import Spond

if TYPE_CHECKING:
    from spond import JSONDict


MOCK_USERNAME, MOCK_PASSWORD = "MOCK_USERNAME", "MOCK_PASSWORD"
MOCK_TOKEN = "MOCK_TOKEN"
MOCK_PAYLOAD = {"accepted": "false", "declineMessage": "sick cannot make it"}


# Mock the `require_authentication` decorator to bypass authentication
def mock_require_authentication(func):
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    return wrapper


_SpondBase.require_authentication = mock_require_authentication(Spond.get_event)


@pytest.fixture
def mock_token() -> str:
    return MOCK_TOKEN


@pytest.fixture
def mock_payload() -> JSONDict:
    return MOCK_PAYLOAD


class TestEventMethods:
    MOCK_EVENT: JSONDict = {
        "id": "ID1",
        "heading": "Event One",
    }

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_event__happy_path(self, mock_get, mock_token) -> None:
        """`get_event()` fetches the singular `sponds/{uid}` endpoint
        (not the list endpoint with filters), so it is not constrained
        by `get_events()`'s default `max_events` cap or
        `include_scheduled=False` filter."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_get.return_value.__aenter__.return_value.ok = True
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=self.MOCK_EVENT
        )

        event = await s.get_event("ID1")

        mock_get.assert_called_once_with(
            "https://api.spond.com/core/v1/sponds/ID1",
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {mock_token}",
            },
            params={"includeComments": "true"},
        )
        assert event == self.MOCK_EVENT

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_event__not_found_raises_keyerror(
        self, mock_get, mock_token
    ) -> None:
        """A 404 from the singular endpoint surfaces as KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_get.return_value.__aenter__.return_value.ok = False
        mock_get.return_value.__aenter__.return_value.status = 404

        with pytest.raises(KeyError):
            await s.get_event("UNKNOWN")

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_event__api_error_raises_valueerror(
        self, mock_get, mock_token
    ) -> None:
        """Other non-2xx responses surface as ValueError with the status."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_get.return_value.__aenter__.return_value.ok = False
        mock_get.return_value.__aenter__.return_value.status = 500
        mock_get.return_value.__aenter__.return_value.text = AsyncMock(
            return_value="Internal Server Error"
        )

        with pytest.raises(ValueError, match="500"):
            await s.get_event("ID1")

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.put")
    async def test_change_response(self, mock_put, mock_payload, mock_token) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

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

        response = await s.change_response(uid="ID1", user="PID3", payload=mock_payload)

        mock_url = "https://api.spond.com/core/v1/sponds/ID1/responses/PID3"
        mock_put.assert_called_once_with(
            mock_url,
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {mock_token}",
            },
            json=mock_payload,
        )
        assert response == mock_response_data


class TestGroupMethods:
    @pytest.fixture
    def mock_groups(self) -> list[JSONDict]:
        """Mock a minimal list of groups."""
        return [
            {
                "id": "ID1",
                "name": "Group One",
            },
            {
                "id": "ID2",
                "name": "Group Two",
            },
        ]

    @pytest.mark.asyncio
    async def test_get_group__happy_path(
        self, mock_groups: list[JSONDict], mock_token
    ) -> None:
        """Test that a valid `id` returns the matching group."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.groups = mock_groups
        s.token = mock_token
        g = await s.get_group("ID2")

        assert g == {
            "id": "ID2",
            "name": "Group Two",
        }

    @pytest.mark.asyncio
    async def test_get_group__no_match_raises_exception(
        self, mock_groups: list[JSONDict], mock_token
    ) -> None:
        """Test that a non-matched `id` raises KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.groups = mock_groups
        s.token = mock_token

        with pytest.raises(KeyError):
            await s.get_group("ID3")

    @pytest.mark.asyncio
    async def test_get_group__blank_id_raises_exception(
        self, mock_groups: list[JSONDict], mock_token
    ) -> None:
        """Test that a blank `id` raises KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.groups = mock_groups
        s.token = mock_token

        with pytest.raises(KeyError):
            await s.get_group("")

    @pytest.mark.asyncio
    async def test_get_group__no_groups_available_raises_keyerror(
        self, mock_token
    ) -> None:
        """`get_groups()` is documented to return None when no groups exist;
        `get_group()` should surface this as KeyError, not TypeError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.groups = None
        s.get_groups = AsyncMock()  # leaves self.groups as None

        with pytest.raises(KeyError):
            await s.get_group("ID1")


class TestExportMethod:
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_export(self, mock_get, mock_token) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_binary = b"\x68\x65\x6c\x6c\x6f\x77\x6f\x72\x6c\x64"  # helloworld
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.read = AsyncMock(
            return_value=mock_binary
        )

        data = await s.get_event_attendance_xlsx(uid="ID1")

        mock_url = "https://api.spond.com/core/v1/sponds/ID1/export"
        mock_get.assert_called_once_with(
            mock_url,
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {mock_token}",
            },
        )
        assert data == mock_binary


class TestPostMethods:
    MOCK_POSTS: list[JSONDict] = [
        {
            "id": "POST1",
            "type": "PLAIN",
            "groupId": "GID1",
            "title": "Post One",
            "body": "Body of post one",
            "timestamp": "2026-03-03T19:20:00.270Z",
            "comments": [],
        },
        {
            "id": "POST2",
            "type": "PLAIN",
            "groupId": "GID2",
            "title": "Post Two",
            "body": "Body of post two",
            "timestamp": "2026-02-20T19:21:20.447Z",
            "comments": [{"id": "C1", "text": "A comment"}],
        },
    ]

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_posts__happy_path(self, mock_get, mock_token) -> None:
        """Test that get_posts returns posts from the API."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_get.return_value.__aenter__.return_value.ok = True
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=self.MOCK_POSTS
        )

        posts = await s.get_posts()

        mock_url = "https://api.spond.com/core/v1/posts/"
        mock_get.assert_called_once_with(
            mock_url,
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {mock_token}",
            },
            params={
                "type": "PLAIN",
                "max": "20",
                "includeComments": "true",
            },
        )
        assert posts == self.MOCK_POSTS
        assert s.posts == self.MOCK_POSTS

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_posts__with_group_id(self, mock_get, mock_token) -> None:
        """Test that group_id is passed as a query parameter."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_get.return_value.__aenter__.return_value.ok = True
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=[self.MOCK_POSTS[0]]
        )

        posts = await s.get_posts(group_id="GID1")

        mock_get.assert_called_once_with(
            "https://api.spond.com/core/v1/posts/",
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {mock_token}",
            },
            params={
                "type": "PLAIN",
                "max": "20",
                "includeComments": "true",
                "groupId": "GID1",
            },
        )
        assert len(posts) == 1

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_posts__custom_max(self, mock_get, mock_token) -> None:
        """Test that max_posts parameter is respected."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_get.return_value.__aenter__.return_value.ok = True
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=[])

        await s.get_posts(max_posts=5)

        call_params = mock_get.call_args[1]["params"]
        assert call_params["max"] == "5"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_posts__no_comments(self, mock_get, mock_token) -> None:
        """Test that include_comments=False is passed correctly."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_get.return_value.__aenter__.return_value.ok = True
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=[])

        await s.get_posts(include_comments=False)

        call_params = mock_get.call_args[1]["params"]
        assert call_params["includeComments"] == "false"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_posts__api_error_raises(self, mock_get, mock_token) -> None:
        """Test that a failed API response raises ValueError."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_get.return_value.__aenter__.return_value.ok = False
        mock_get.return_value.__aenter__.return_value.status = 401
        mock_get.return_value.__aenter__.return_value.text = AsyncMock(
            return_value="Unauthorized"
        )

        with pytest.raises(ValueError, match="401"):
            await s.get_posts()


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
