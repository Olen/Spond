"""Tests for messaging — both the low-level `Spond.send_message()` entrypoint
and the typed `Chat`/`Message` surface returned by `Spond.get_messages()`."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from spond.spond import Spond

from .conftest import MOCK_PASSWORD, MOCK_TOKEN, MOCK_USERNAME


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

    def test_chat_str(self) -> None:
        """`Chat.__str__` includes uid, name, and type."""
        from spond.chat import Chat

        c = Chat.from_api(self._CHAT_PAYLOAD, None)
        s = str(c)
        assert "CHAT1" in s
        assert "Demo Group" in s
        assert "GROUP" in s

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


class TestGetMessages:
    """Tests for `Spond.get_messages()` — chat-server handshake and list
    returned as typed Chat instances."""

    _CHAT_PAYLOAD = {
        "id": "CHAT1",
        "name": "Demo",
        "type": "GROUP",
        "participants": ["P1"],
        "newestTimestamp": "2026-05-14T12:00:00Z",
        "unread": False,
        "muted": False,
    }

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_messages_happy_path(self, mock_get, mock_token) -> None:
        """get_messages() returns a list of Chat objects and caches on
        `self.messages`. The chat-server token is pre-set so `_login_chat`
        is not triggered."""
        from spond.chat import Chat

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s._auth = "MOCK_CHAT_AUTH"
        s._chat_url = "https://chat.example.invalid"

        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=[self._CHAT_PAYLOAD]
        )

        messages = await s.get_messages()

        assert messages is not None
        assert len(messages) == 1
        assert isinstance(messages[0], Chat)
        assert messages[0].uid == "CHAT1"
        assert s.messages is messages

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_messages_returns_none_when_api_returns_null(
        self, mock_get, mock_token
    ) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s._auth = "MOCK_CHAT_AUTH"
        s._chat_url = "https://chat.example.invalid"

        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=None)

        messages = await s.get_messages()
        assert messages is None
        assert s.messages is None

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_messages_max_chats_param(self, mock_get, mock_token) -> None:
        """The `max` query parameter must reflect the `max_chats` argument."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s._auth = "MOCK_CHAT_AUTH"
        s._chat_url = "https://chat.example.invalid"

        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=[])

        await s.get_messages(max_chats=50)

        params = mock_get.call_args[1]["params"]
        assert params["max"] == "50"


class TestSendMessageNewChat:
    """Tests for `Spond.send_message()` when starting a *new* chat
    (user + group_uid path, lines 489-506 in spond.py)."""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_send_message_new_chat_happy_path(
        self, mock_post, mock_token
    ) -> None:
        """With `user` and `group_uid`, `send_message()` looks up the member
        by `get_person()`, extracts `profile.id`, and POSTs to the chat server."""
        from spond.group import Group

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s._auth = "MOCK_CHAT_AUTH"
        s._chat_url = "https://chat.example.invalid"
        # Pre-populate groups so get_person() resolves locally
        s.groups = [
            Group.model_validate({
                "id": "GID1",
                "name": "G",
                "members": [{
                    "id": "M1",
                    "firstName": "Alice",
                    "lastName": "Smith",
                    "profile": {"id": "PROF1"},
                }],
            })
        ]

        api_response = {"ok": True, "messageId": "MSG1"}
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=api_response
        )

        result = await s.send_message(
            text="Hello", user="M1", group_uid="GID1"
        )

        assert result == api_response
        kwargs = mock_post.call_args[1]
        assert kwargs["json"]["recipient"] == "PROF1"
        assert kwargs["json"]["groupId"] == "GID1"
        assert kwargs["json"]["text"] == "Hello"
        assert kwargs["json"]["type"] == "TEXT"

    @pytest.mark.asyncio
    async def test_send_message_user_without_profile_raises(
        self, mock_token
    ) -> None:
        """If the located member has no `profile` dict with an `id`, a clear
        `ValueError` is raised rather than crashing inside the POST."""
        from spond.group import Group

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s._auth = "MOCK_CHAT_AUTH"
        s._chat_url = "https://chat.example.invalid"
        s.groups = [
            Group.model_validate({
                "id": "GID1",
                "name": "G",
                "members": [{
                    "id": "M2",
                    "firstName": "Bob",
                    "lastName": "Jones",
                    # no profile → profile is None
                }],
            })
        ]

        with pytest.raises(ValueError, match="profile id"):
            await s.send_message(text="hi", user="M2", group_uid="GID1")


class TestMemberSendMessage:
    """Tests for `Member.send_message()` and `Guardian.send_message()` —
    the per-instance HTTP helpers on `person.py`."""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_member_send_message_routes_to_chat_server(
        self, mock_post, mock_token
    ) -> None:
        """Calling `member.send_message()` POSTs the correct payload to the
        chat-server host with the chat-server auth header."""
        from spond.group import Group

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s._auth = "CHAT_AUTH"
        s._chat_url = "https://chat.example.invalid"

        group = Group.from_api(
            {
                "id": "GID",
                "name": "G",
                "members": [{
                    "id": "M1",
                    "firstName": "A",
                    "lastName": "B",
                    "profile": {"id": "PROF1"},
                }],
            },
            s,
        )
        member = group.members[0]

        api_response = {"ok": True}
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=api_response
        )

        result = await member.send_message("test msg", "GID")

        assert result == api_response
        kwargs = mock_post.call_args[1]
        assert kwargs["json"]["recipient"] == "PROF1"
        assert kwargs["json"]["groupId"] == "GID"
        assert kwargs["json"]["text"] == "test msg"
        assert kwargs["headers"] == {"auth": "CHAT_AUTH"}

    def test_member_send_message_without_client_raises(self) -> None:
        """A Member instantiated without a client (e.g. test fixture) must
        raise `RuntimeError` rather than crashing with AttributeError."""
        import asyncio

        from spond.person import Member

        m = Member.model_validate(
            {"id": "M1", "firstName": "A", "lastName": "B", "profile": {"id": "P1"}}
        )
        # _client is None — no Group.from_api() was called
        with pytest.raises(RuntimeError, match="no client"):
            asyncio.run(m.send_message("hello", "GID"))

    @pytest.mark.asyncio
    async def test_member_send_message_without_profile_id_raises(self) -> None:
        """If the member has no `profile.id`, a clear `ValueError` is raised
        (not an AttributeError inside the send path)."""
        from spond.person import Member

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s._auth = "CHAT_AUTH"
        s._chat_url = "https://chat.example.invalid"

        m = Member.model_validate({"id": "M1", "firstName": "A", "lastName": "B"})
        m._client = s  # wire client, but no profile

        with pytest.raises(ValueError, match="profile id"):
            await m.send_message("hello", "GID")

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_guardian_send_message_routes_to_chat_server(
        self, mock_post, mock_token
    ) -> None:
        """Guardian.send_message() uses the same `_send_message_to_person`
        helper as Member.send_message() — verify it also works."""
        from spond.group import Group

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s._auth = "CHAT_AUTH"
        s._chat_url = "https://chat.example.invalid"

        group = Group.from_api(
            {
                "id": "GID",
                "name": "G",
                "members": [{
                    "id": "M1",
                    "firstName": "Child",
                    "lastName": "A",
                    "guardians": [{
                        "id": "G1",
                        "firstName": "Parent",
                        "lastName": "A",
                        "profile": {"id": "PROF_G1"},
                    }],
                }],
            },
            s,
        )
        guardian = group.members[0].guardians[0]

        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={"ok": True}
        )

        result = await guardian.send_message("guardian msg", "GID")

        assert result == {"ok": True}
        kwargs = mock_post.call_args[1]
        assert kwargs["json"]["recipient"] == "PROF_G1"


class TestLazyChatLogin:
    """Tests for the lazy `_login_chat()` handshake path — verifies that
    `get_messages()`, `_continue_chat()`, `send_message()`, `chat.send()`,
    and `member.send_message()` all trigger `_login_chat()` when `_auth` is
    None, and that `_login_chat()` itself correctly stores the chat-server
    URL and token from the API response."""

    _CHAT_HANDSHAKE = {
        "url": "https://chat.example.invalid",
        "auth": "FRESH_CHAT_AUTH",
    }

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    @patch("aiohttp.ClientSession.post")
    async def test_login_chat_sets_url_and_auth(
        self, mock_post, mock_get
    ) -> None:
        """`_login_chat()` must POST to `{api_url}chat`, then store the
        returned `url` and `auth` on the client instance."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = MOCK_TOKEN
        # _auth and _chat_url are None — trigger lazy login

        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=self._CHAT_HANDSHAKE
        )
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=[]
        )

        await s.get_messages()

        assert s._chat_url == "https://chat.example.invalid"
        assert s._auth == "FRESH_CHAT_AUTH"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    @patch("aiohttp.ClientSession.post")
    async def test_get_messages_triggers_lazy_login(
        self, mock_post, mock_get
    ) -> None:
        """`get_messages()` must call `_login_chat()` when `_auth` is None."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = MOCK_TOKEN

        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=self._CHAT_HANDSHAKE
        )
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=[]
        )

        messages = await s.get_messages()

        # One POST for _login_chat, zero POSTs otherwise; one GET for chats
        mock_post.assert_called_once()
        assert messages == []

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_continue_chat_triggers_lazy_login(self, mock_post) -> None:
        """`_continue_chat()` independently calls `_login_chat()` when its
        own `_auth` guard fires — covers line 420 in spond.py."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = MOCK_TOKEN
        # _auth=None and _chat_url=None: _continue_chat must bootstrap both

        # Side-effect: first call is _login_chat POST, second is the message POST
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            side_effect=[
                self._CHAT_HANDSHAKE,  # _login_chat response
                {"ok": True},          # message send response
            ]
        )

        result = await s._continue_chat("CHAT1", "hello")

        assert result == {"ok": True}
        assert s._auth == "FRESH_CHAT_AUTH"
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_send_message_chat_id_triggers_lazy_login(
        self, mock_post
    ) -> None:
        """`send_message(chat_id=...)` calls `_login_chat()` when `_auth` is
        None — covers line 479 in spond.py."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = MOCK_TOKEN

        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            side_effect=[
                self._CHAT_HANDSHAKE,
                {"ok": True},
            ]
        )

        result = await s.send_message(text="hi", chat_id="CHAT1")

        assert result == {"ok": True}
        assert s._auth == "FRESH_CHAT_AUTH"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_chat_send_triggers_lazy_login_on_client(
        self, mock_post
    ) -> None:
        """`chat.send()` triggers `_client._login_chat()` when `_client._auth`
        is None — covers chat.py:158."""
        from spond.chat import Chat

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = MOCK_TOKEN
        # _auth is None — the chat's send() must bootstrap it

        chat = Chat.from_api(
            {
                "id": "CHAT1",
                "name": "G",
                "type": "GROUP",
                "participants": [],
                "newestTimestamp": "2026-01-01T00:00:00Z",
                "unread": False,
                "muted": False,
            },
            s,
        )

        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            side_effect=[
                self._CHAT_HANDSHAKE,  # _login_chat
                {"ok": True},          # message send
            ]
        )

        result = await chat.send("ack")

        assert result == {"ok": True}
        assert s._auth == "FRESH_CHAT_AUTH"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_member_send_message_triggers_lazy_login(
        self, mock_post
    ) -> None:
        """`member.send_message()` calls `_login_chat()` when the client's
        `_auth` is None — covers person.py:174."""
        from spond.group import Group

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = MOCK_TOKEN
        # _auth is None; _send_message_to_person must bootstrap it

        group = Group.from_api(
            {
                "id": "GID",
                "name": "G",
                "members": [{
                    "id": "M1",
                    "firstName": "A",
                    "lastName": "B",
                    "profile": {"id": "PROF1"},
                }],
            },
            s,
        )
        member = group.members[0]

        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            side_effect=[
                self._CHAT_HANDSHAKE,
                {"ok": True},
            ]
        )

        result = await member.send_message("hello", "GID")

        assert result == {"ok": True}
        assert s._auth == "FRESH_CHAT_AUTH"
