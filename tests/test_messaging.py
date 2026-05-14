"""Tests for messaging — both the low-level `Spond.send_message()` entrypoint
and the typed `Chat`/`Message` surface returned by `Spond.get_messages()`."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from spond.spond import Spond

from .conftest import MOCK_PASSWORD, MOCK_USERNAME


class TestSendMessage:
    """Tests for `Spond.send_message()` — covers the fixes in #238."""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_send_message__continues_chat_when_chat_id_given(
        self, mock_post, mock_token
    ) -> None:
        """With `chat_id`, the call should route through `_continue_chat()`
        and properly await it (regression: the await was missing).
        `_continue_chat` now uses `async with`, so the post mock follows
        the standard context-manager pattern used elsewhere in this file.
        """
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s._auth = "MOCK_CHAT_AUTH"
        s._chat_url = "https://chat.example.invalid"

        api_response = {"ok": True, "messageId": "MID1"}
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=api_response
        )

        result = await s.send_message(text="hello", chat_id="CHAT1")

        assert result == api_response
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == {"chatId": "CHAT1", "text": "hello", "type": "TEXT"}

    @pytest.mark.asyncio
    async def test_send_message__missing_args_raises_valueerror(
        self, mock_token
    ) -> None:
        """Without `chat_id` and without both `user` and `group_uid`, the
        call should raise rather than silently return a sentinel dict."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s._auth = "MOCK_CHAT_AUTH"
        s._chat_url = "https://chat.example.invalid"

        with pytest.raises(ValueError, match="chat_id"):
            await s.send_message(text="hello")

        with pytest.raises(ValueError, match="user and group_uid"):
            await s.send_message(text="hello", user="USER1")

        with pytest.raises(ValueError, match="user and group_uid"):
            await s.send_message(text="hello", group_uid="GROUP1")


class TestChat:
    """Chat/Message typed surface — replaces the old `list[JSONDict]` return
    from `Spond.get_messages()`."""

    _CHAT_PAYLOAD = {
        "id": "CHAT1",
        "name": "Demo Group",
        "type": "GROUP",
        "participants": ["P1", "P2"],
        "newestTimestamp": "2026-05-14T12:00:00Z",
        "unread": True,
        "muted": False,
        "message": {
            "chatId": "CHAT1",
            "msgNum": 42,
            "type": "TEXT",
            "timestamp": "2026-05-14T12:00:00Z",
            "text": "hello",
            "user": "P1",
        },
    }

    def test_chat_parses_with_typed_message(self) -> None:
        from spond.chat import Chat, Message

        c = Chat.from_api(self._CHAT_PAYLOAD, None)
        assert c.uid == "CHAT1"
        assert c.name == "Demo Group"
        assert c.type == "GROUP"
        assert c.unread is True
        assert c.participants == ["P1", "P2"]
        assert isinstance(c.message, Message)
        assert c.message.type == "TEXT"
        assert c.message.text == "hello"
        assert c.message.user == "P1"

    def test_chat_message_optional_for_resilience(self) -> None:
        """A chat with no embedded message (rare but possible) must not crash
        — the only required field on Chat is `uid`."""
        from spond.chat import Chat

        c = Chat.from_api({"id": "X"}, None)
        assert c.uid == "X"
        assert c.message is None

    def test_message_type_specific_extras_default_to_empty(self) -> None:
        """A TEXT message must not falsely report `new_name` or `images` —
        those are RENAME/IMAGES-specific."""
        from spond.chat import Message

        m = Message.model_validate(self._CHAT_PAYLOAD["message"])
        assert m.new_name is None
        assert m.images == []
        assert m.internal_promo is None
        assert m.campaign is None

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_chat_send_routes_through_chat_server(
        self, mock_post, mock_token
    ) -> None:
        """`chat.send(text)` posts to the chat-server host with the chat-server
        auth token (not the regular Bearer), preserving the same wire shape
        the deprecated `Spond.send_message(chat_id=...)` path uses."""
        from spond.chat import Chat

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s._auth = "MOCK_CHAT_AUTH"
        s._chat_url = "https://chat.example.invalid"

        chat = Chat.from_api(self._CHAT_PAYLOAD, s)
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={"ok": True}
        )
        result = await chat.send("ack")
        assert result == {"ok": True}
        url, _ = mock_post.call_args[0], mock_post.call_args[1]
        assert url[0] == "https://chat.example.invalid/messages"
        kwargs = mock_post.call_args[1]
        assert kwargs["json"] == {"chatId": "CHAT1", "text": "ack", "type": "TEXT"}
        assert kwargs["headers"] == {"auth": "MOCK_CHAT_AUTH"}

    def test_chat_send_refuses_without_client(self) -> None:
        """A Chat constructed without a client (test fixture, direct
        instantiation) must raise rather than crashing with an attribute
        error inside the send path."""
        import asyncio

        from spond.chat import Chat

        c = Chat.from_api(self._CHAT_PAYLOAD, None)
        with pytest.raises(RuntimeError, match="no client attached"):
            asyncio.run(c.send("hello"))
