"""Tests for `Spond.get_posts()` — query-parameter construction, caching,
and error surfacing."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from spond.spond import Spond

from .conftest import MOCK_PASSWORD, MOCK_USERNAME

if TYPE_CHECKING:
    from spond import JSONDict


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
        assert posts is not None
        assert len(posts) == 2
        assert posts[0].uid == "POST1"
        assert posts[0].title == "Post One"
        assert posts[1].uid == "POST2"
        assert s.posts is posts  # cache identity

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

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_posts__returns_none_when_api_returns_null(
        self, mock_get, mock_token
    ) -> None:
        """When the API returns null, `get_posts()` returns None and sets
        `self.posts = None`."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_get.return_value.__aenter__.return_value.ok = True
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=None
        )

        result = await s.get_posts()
        assert result is None
        assert s.posts is None
