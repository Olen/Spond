"""Tests for the ActiveRecord write surface on Post: `save()`,
`delete()`, and `add_comment()`.

Mirrors `tests/test_event_save_delete.py` — same dispatch shape, same
backward-compat guards. Endpoints (`POST /posts/`,
`DELETE /posts/{uid}`, `POST /posts/{uid}/comments`) verified live
against the test group before these tests were written; this file
locks in the wire shape so future refactors can't drift."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from spond import SpondAPIError
from spond.comment import Comment
from spond.post import Post
from spond.spond import Spond

from .conftest import MOCK_PASSWORD, MOCK_USERNAME


def _fresh_post() -> Post:
    """Build an unsaved Post (no uid)."""
    return Post(
        uid="",
        type="PLAIN",
        group_uid="GROUP1",
        title="New Post",
        body="Some content.",
    )


_API_POST = {
    "id": "NEWUID",
    "type": "PLAIN",
    "groupId": "GROUP1",
    "title": "New Post",
    "body": "Some content.",
    "ownerId": "PROFILE1",
    "timestamp": "2026-05-15T10:00:00Z",
    "comments": [],
}


class TestPostSaveCreate:
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_create_populates_uid_in_place(self, mock_post) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        post = _fresh_post()

        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=_API_POST
        )

        result = await post.save(client=s)

        # save() returns self (mutated in place)
        assert result is post
        assert post.uid == "NEWUID"
        assert post.owner_uid == "PROFILE1"
        assert post.timestamp is not None
        assert post._client is s

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_create_posts_to_collection_url(self, mock_post) -> None:
        """Create POSTs to `/posts/` (no uid in path)."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        post = _fresh_post()

        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=_API_POST
        )

        await post.save(client=s)

        called_url = mock_post.call_args[0][0]
        assert called_url.endswith("/posts/")

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_create_payload_excludes_server_managed(self, mock_post) -> None:
        """The create payload includes user-set fields but NOT `id`
        (Spond mints the uid)."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        post = _fresh_post()

        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=_API_POST
        )

        await post.save(client=s)

        posted = mock_post.call_args[1]["json"]
        assert "id" not in posted
        assert posted["title"] == "New Post"
        assert posted["groupId"] == "GROUP1"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_create_prepends_to_cache(self, mock_post) -> None:
        """A newly-saved post is prepended to `posts` (position 0) — same
        ordering convention as `Event.save()`, matching Spond's
        newest-first ordering on `get_posts()`."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        existing = Post.from_api({**_API_POST, "id": "EXISTING"}, s)
        s.posts = [existing]
        post = _fresh_post()

        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=_API_POST
        )

        await post.save(client=s)

        # New post at position 0; existing post slid down.
        assert len(s.posts) == 2
        assert s.posts[0].uid == "NEWUID"
        assert s.posts[1].uid == "EXISTING"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_create_initialises_empty_cache(self, mock_post) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        s.posts = None
        post = _fresh_post()

        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=_API_POST
        )

        await post.save(client=s)
        assert s.posts == [post]

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_create_raises_on_http_error(self, mock_post) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        post = _fresh_post()

        mock_post.return_value.__aenter__.return_value.ok = False
        mock_post.return_value.__aenter__.return_value.status = 500
        mock_post.return_value.__aenter__.return_value.text = AsyncMock(
            return_value="boom"
        )

        with pytest.raises(SpondAPIError) as exc_info:
            await post.save(client=s)
        assert exc_info.value.status == 500

    @pytest.mark.asyncio
    async def test_save_without_client_raises(self) -> None:
        post = _fresh_post()
        with pytest.raises(RuntimeError, match="no client bound"):
            await post.save()


class TestPostSaveUpdate:
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_save_existing_posts_to_uid_url(self, mock_post) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        post = Post.from_api(_API_POST, s)

        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={**_API_POST, "title": "Renamed"}
        )

        post.title = "Renamed"
        await post.save()

        called_url = mock_post.call_args[0][0]
        assert called_url.endswith("/posts/NEWUID")
        assert post.title == "Renamed"


class TestPostDelete:
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.delete")
    async def test_delete_issues_delete(self, mock_delete) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        post = Post.from_api(_API_POST, s)
        s.posts = [post]

        mock_delete.return_value.__aenter__.return_value.ok = True

        await post.delete()

        called_url = mock_delete.call_args[0][0]
        assert called_url.endswith("/posts/NEWUID")
        assert s.posts == []

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.delete")
    async def test_delete_prunes_only_target_from_cache(self, mock_delete) -> None:
        """Other posts in the cache must survive an unrelated delete."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        p1 = Post.from_api({**_API_POST, "id": "DELME"}, s)
        p2 = Post.from_api({**_API_POST, "id": "KEEP"}, s)
        s.posts = [p1, p2]

        mock_delete.return_value.__aenter__.return_value.ok = True

        await p1.delete()
        assert [p.uid for p in s.posts] == ["KEEP"]

    @pytest.mark.asyncio
    async def test_delete_without_client_raises(self) -> None:
        post = Post.model_validate(_API_POST)
        with pytest.raises(RuntimeError, match="no client"):
            await post.delete()

    @pytest.mark.asyncio
    async def test_delete_without_uid_raises(self) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        post = _fresh_post()
        post._client = s
        with pytest.raises(RuntimeError, match="unsaved"):
            await post.delete()

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.delete")
    async def test_delete_raises_on_http_error(self, mock_delete) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        post = Post.from_api(_API_POST, s)

        mock_delete.return_value.__aenter__.return_value.ok = False
        mock_delete.return_value.__aenter__.return_value.status = 403
        mock_delete.return_value.__aenter__.return_value.text = AsyncMock(
            return_value="nope"
        )

        with pytest.raises(SpondAPIError):
            await post.delete()


class TestAddComment:
    _API_COMMENT = {
        "id": "CMT1",
        "fromProfileId": "PROF1",
        "timestamp": "2026-05-15T11:00:00Z",
        "text": "Hello there",
        "reactions": {},
    }

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_add_comment_returns_typed_comment(self, mock_post) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        post = Post.from_api(_API_POST, s)

        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=self._API_COMMENT
        )

        result = await post.add_comment("Hello there")
        assert isinstance(result, Comment)
        assert result.uid == "CMT1"
        assert result.text == "Hello there"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_add_comment_posts_to_comments_endpoint(self, mock_post) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        post = Post.from_api(_API_POST, s)

        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=self._API_COMMENT
        )

        await post.add_comment("Hello there")

        called_url = mock_post.call_args[0][0]
        assert called_url.endswith("/posts/NEWUID/comments")
        # Body shape: just {"text": ...}
        body = mock_post.call_args[1]["json"]
        assert body == {"text": "Hello there"}

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_add_comment_appends_to_post_comments(self, mock_post) -> None:
        """After `add_comment()`, `post.comments` contains the new comment
        without an explicit refresh."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        post = Post.from_api(_API_POST, s)
        assert len(post.comments) == 0

        mock_post.return_value.__aenter__.return_value.ok = True
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=self._API_COMMENT
        )

        c = await post.add_comment("Hello there")
        assert len(post.comments) == 1
        assert post.comments[0] is c

    @pytest.mark.asyncio
    async def test_add_comment_without_client_raises(self) -> None:
        post = Post.model_validate(_API_POST)
        with pytest.raises(RuntimeError, match="no client"):
            await post.add_comment("hi")

    @pytest.mark.asyncio
    async def test_add_comment_without_uid_raises(self) -> None:
        """Can't comment on an unsaved Post — no parent uid for the URL."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        post = _fresh_post()
        post._client = s
        with pytest.raises(RuntimeError, match="unsaved"):
            await post.add_comment("hi")

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_add_comment_raises_on_http_error(self, mock_post) -> None:
        """E.g. when `commentsDisabled=True` on the post Spond rejects."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        post = Post.from_api(_API_POST, s)

        mock_post.return_value.__aenter__.return_value.ok = False
        mock_post.return_value.__aenter__.return_value.status = 403
        mock_post.return_value.__aenter__.return_value.text = AsyncMock(
            return_value="comments disabled"
        )

        with pytest.raises(SpondAPIError):
            await post.add_comment("hi")


class TestPostRoundtrip:
    """End-to-end ActiveRecord lifecycle: construct → save (create) →
    mutate → save (update) → add_comment → delete."""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.delete")
    @patch("aiohttp.ClientSession.post")
    async def test_full_lifecycle(self, mock_post, mock_delete) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = "MOCK"
        s.posts = []
        post = _fresh_post()

        mock_post.return_value.__aenter__.return_value.ok = True
        # Sequence: create response, update response, comment response
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            side_effect=[
                _API_POST,
                {**_API_POST, "title": "Renamed"},
                {
                    "id": "CMT",
                    "text": "hi",
                    "fromProfileId": "P",
                    "timestamp": "2026-05-15T12:00:00Z",
                },
            ]
        )

        await post.save(client=s)
        assert post.uid == "NEWUID"

        post.title = "Renamed"
        await post.save()
        assert post.title == "Renamed"

        c = await post.add_comment("hi")
        assert c.text == "hi"
        assert post.comments[-1] is c

        mock_delete.return_value.__aenter__.return_value.ok = True
        await post.delete()
        assert post.uid not in {p.uid for p in s.posts}
