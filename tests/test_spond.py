"""Test suite for Spond class."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from spond import AuthenticationError
from spond.base import _SpondBase
from spond.event import Event
from spond.group import Group
from spond.spond import Spond

if TYPE_CHECKING:
    from spond import JSONDict


# Minimum-viable Event API payload — all required fields filled with placeholder
# data. Tests that need an Event object can spread/override.
_MIN_EVENT_PAYLOAD: dict = {
    "id": "ID1",
    "heading": "Event One",
    "startTimestamp": "2026-01-01T10:00:00Z",
    "endTimestamp": "2026-01-01T11:00:00Z",
    "createdTime": "2025-12-01T10:00:00Z",
    "type": "EVENT",
    "responses": {
        "acceptedIds": [],
        "declinedIds": [],
        "unansweredIds": [],
        "waitinglistIds": [],
        "unconfirmedIds": [],
    },
}


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
    @pytest.fixture
    def mock_events(self) -> list[Event]:
        """Two typed Event instances with placeholder data."""
        return [
            Event.model_validate(
                {**_MIN_EVENT_PAYLOAD, "id": "ID1", "heading": "Event One"}
            ),
            Event.model_validate(
                {**_MIN_EVENT_PAYLOAD, "id": "ID2", "heading": "Event Two"}
            ),
        ]

    @pytest.mark.asyncio
    async def test_get_event__happy_path(
        self, mock_events: list[Event], mock_token
    ) -> None:
        """Test that a valid `id` returns the matching event."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.events = mock_events
        s.token = mock_token
        g = await s.get_event("ID1")

        assert isinstance(g, Event)
        assert g.uid == "ID1"
        assert g.heading == "Event One"

    @pytest.mark.asyncio
    async def test_get_event__no_match_raises_exception(
        self, mock_events: list[Event], mock_token
    ) -> None:
        """Test that a non-matched `id` raises KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.events = mock_events
        s.token = mock_token

        with pytest.raises(KeyError):
            await s.get_event("ID3")

    @pytest.mark.asyncio
    async def test_get_event__blank_id_match_raises_exception(
        self, mock_events: list[Event], mock_token
    ) -> None:
        """Test that a blank `id` raises KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.events = mock_events
        s.token = mock_token

        with pytest.raises(KeyError):
            await s.get_event("")

    @pytest.mark.asyncio
    async def test_get_event__no_events_available_raises_keyerror(
        self, mock_token
    ) -> None:
        """`get_events()` is documented to return None when no events exist;
        `get_event()` should surface this as KeyError, not TypeError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.events = None
        s.get_events = AsyncMock()  # leaves self.events as None

        with pytest.raises(KeyError):
            await s.get_event("ID1")

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_update_event__returns_api_response(
        self, mock_post, mock_token
    ) -> None:
        """Deprecated `Spond.update_event()` should still return the POST response
        as a dict for backward compatibility (delegates to `Event.update()`)."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.events = [Event.from_api(_MIN_EVENT_PAYLOAD, s)]

        api_response = {**_MIN_EVENT_PAYLOAD, "heading": "New"}
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=api_response
        )

        import warnings as _warnings

        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            result = await s.update_event(uid="ID1", updates={"heading": "New"})

        # Deprecation warning fired
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
        # Result is a dict (model_dump output), with the updated heading
        assert isinstance(result, dict)
        assert result["heading"] == "New"
        # Regression guard for issue #239: the result must NOT be the
        # cached events list (the bug that was: `return self.events`).
        assert result is not s.events

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.put")
    async def test_change_response(self, mock_put, mock_payload, mock_token) -> None:
        """Deprecated `Spond.change_response()` should still PUT to the same URL
        and return the API response (delegates to `Event.change_response()`)."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        s.events = [Event.from_api(_MIN_EVENT_PAYLOAD, s)]

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

        import warnings as _warnings

        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            response = await s.change_response(
                uid="ID1", user="PID3", payload=mock_payload
            )

        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
        mock_url = "https://api.spond.com/core/v1/sponds/ID1/responses/PID3"
        # The wrapper forwards `payload` verbatim — same bytes that go on
        # the wire on the pre-OO code path.
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
    def mock_groups(self) -> list[Group]:
        """Two typed Group instances with placeholder data."""
        return [
            Group.model_validate({"id": "ID1", "name": "Group One"}),
            Group.model_validate({"id": "ID2", "name": "Group Two"}),
        ]

    @pytest.mark.asyncio
    async def test_get_group__happy_path(
        self, mock_groups: list[Group], mock_token
    ) -> None:
        """Test that a valid `id` returns the matching group."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.groups = mock_groups
        s.token = mock_token
        g = await s.get_group("ID2")

        assert isinstance(g, Group)
        assert g.uid == "ID2"
        assert g.name == "Group Two"

    @pytest.mark.asyncio
    async def test_get_group__no_match_raises_exception(
        self, mock_groups: list[Group], mock_token
    ) -> None:
        """Test that a non-matched `id` raises KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.groups = mock_groups
        s.token = mock_token

        with pytest.raises(KeyError):
            await s.get_group("ID3")

    @pytest.mark.asyncio
    async def test_get_group__blank_id_raises_exception(
        self, mock_groups: list[Group], mock_token
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


class TestExportMethod:
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_export(self, mock_get, mock_token) -> None:
        """Deprecated `Spond.get_event_attendance_xlsx()` should still GET the
        export endpoint and return raw bytes (delegates to
        `Event.attendance_xlsx()`)."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        # Note: `s.events` is intentionally not pre-populated — the
        # deprecated wrapper does a direct GET on the export endpoint, it
        # doesn't consult the events cache.

        mock_binary = b"\x68\x65\x6c\x6c\x6f\x77\x6f\x72\x6c\x64"  # helloworld
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.read = AsyncMock(
            return_value=mock_binary
        )

        import warnings as _warnings

        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            data = await s.get_event_attendance_xlsx(uid="ID1")

        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
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


# =============================================================================
# OO rewrite tests — typed-object ActiveRecord surface, dict-compat shim,
# inter-dependency navigation. See DESIGN-oo-rewrite.md for context.
# =============================================================================


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
        # Profile with no name fields — same relaxation
        pr = Profile.model_validate({"id": "PR1"})
        assert pr.first_name == ""

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
        assert p.newSpondField == 42  # native attribute access via Pydantic

        g = Group.model_validate({"id": "G1", "name": "GG", "newGroupAttr": ["x"]})
        assert "newGroupAttr" in g
        assert g.newGroupAttr == ["x"]


class TestEventOOMethods:
    """ActiveRecord methods on Event."""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_event_update_returns_new_event(self, mock_post, mock_token) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)

        api_response = {**_MIN_EVENT_PAYLOAD, "heading": "Updated"}
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=api_response
        )

        result = await event.update(heading="Updated")
        assert isinstance(result, Event)
        assert result.heading == "Updated"
        assert result is not event  # immutable: returns new

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_event_update_accepts_positional_dict(
        self, mock_post, mock_token
    ) -> None:
        """`event.update(updates_dict)` works for keys that would clash with
        reserved kwargs when passed via `**` (e.g. `self`, `cls`)."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)

        api_response = {**_MIN_EVENT_PAYLOAD, "heading": "New"}
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=api_response
        )

        # Use the positional dict form
        result = await event.update({"heading": "New", "selfish": "any"})
        assert result.heading == "New"
        # Unknown key "selfish" was passed through to the API payload
        posted = mock_post.call_args[1]["json"]
        assert posted["selfish"] == "any"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_event_update_refreshes_client_cache(
        self, mock_post, mock_token
    ) -> None:
        """After `event.update()`, the client's events cache must hold the
        new instance — not the stale pre-update one — so subsequent
        `spond.get_event(uid)` calls return current state."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        original = Event.from_api(_MIN_EVENT_PAYLOAD, s)
        s.events = [original]

        api_response = {**_MIN_EVENT_PAYLOAD, "heading": "Refreshed"}
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=api_response
        )

        result = await original.update(heading="Refreshed")
        # Cache must now point at the new instance (in-place replacement
        # preserves the list identity for callers holding `s.events`).
        assert s.events is not None
        assert s.events[0] is result
        assert s.events[0].heading == "Refreshed"
        assert s.events[0] is not original

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.put")
    async def test_event_change_response_accepts(self, mock_put, mock_token) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)

        mock_put.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={"acceptedIds": ["MID1"]}
        )
        result = await event.change_response("MID1", accepted=True)
        assert result == {"acceptedIds": ["MID1"]}
        call_args = mock_put.call_args
        assert call_args[0][0].endswith("/sponds/ID1/responses/MID1")
        assert call_args[1]["json"]["accepted"] == "true"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.put")
    async def test_event_change_response_declines_with_message(
        self, mock_put, mock_token
    ) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)

        mock_put.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={"declinedIds": ["MID1"]}
        )
        await event.change_response("MID1", accepted=False, decline_message="busy")
        sent = mock_put.call_args[1]["json"]
        assert sent["accepted"] == "false"
        assert sent["declineMessage"] == "busy"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_event_attendance_xlsx_returns_bytes(
        self, mock_get, mock_token
    ) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        event = Event.from_api(_MIN_EVENT_PAYLOAD, s)

        mock_get.return_value.__aenter__.return_value.read = AsyncMock(
            return_value=b"PKxlsx-bytes"
        )
        data = await event.attendance_xlsx()
        assert data == b"PKxlsx-bytes"
        assert mock_get.call_args[0][0].endswith("/sponds/ID1/export")


class TestGroupNavigation:
    """Group → Member → Guardian wiring."""

    def test_group_materializes_typed_members_and_guardians(self) -> None:
        raw = {
            "id": "GID",
            "name": "Test Group",
            "members": [
                {
                    "id": "M1",
                    "firstName": "Alice",
                    "lastName": "Smith",
                    "email": "alice@example.invalid",
                    "guardians": [
                        {
                            "id": "G1",
                            "firstName": "Bob",
                            "lastName": "Smith",
                            "phoneNumber": "+1",
                        }
                    ],
                },
            ],
        }
        from spond.person import Guardian, Member

        group = Group.model_validate(raw)
        assert isinstance(group.members[0], Member)
        assert group.members[0].full_name == "Alice Smith"
        assert isinstance(group.members[0].guardians[0], Guardian)
        assert group.members[0].guardians[0].full_name == "Bob Smith"

    def test_find_member_by_email(self) -> None:
        group = Group.model_validate(
            {
                "id": "GID",
                "name": "G",
                "members": [
                    {
                        "id": "M1",
                        "firstName": "A",
                        "lastName": "B",
                        "email": "a@b.invalid",
                    },
                ],
            }
        )
        found = group.find_member(email="a@b.invalid")
        assert found is not None
        assert found.uid == "M1"

    def test_find_member_returns_none_when_no_match(self) -> None:
        group = Group.model_validate({"id": "GID", "name": "G", "members": []})
        assert group.find_member(uid="missing") is None

    def test_find_member_requires_exactly_one_criterion(self) -> None:
        group = Group.model_validate({"id": "GID", "name": "G", "members": []})
        with pytest.raises(ValueError, match="exactly one"):
            group.find_member()
        with pytest.raises(ValueError, match="exactly one"):
            group.find_member(uid="X", email="a@b.invalid")

    def test_member_custom_fields_alias_works_via_either_name(self) -> None:
        """`Member.custom_fields` aliases the API's `"fields"` key — both
        forms must populate the attribute identically."""
        from spond.person import Member

        # API-style (via alias):
        m1 = Member.model_validate(
            {"id": "M1", "firstName": "A", "lastName": "B", "fields": {"height": "175"}}
        )
        # Python-style (via name):
        m2 = Member.model_validate(
            {
                "id": "M2",
                "firstName": "C",
                "lastName": "D",
                "custom_fields": {"height": "180"},
            }
        )
        assert m1.custom_fields == {"height": "175"}
        assert m2.custom_fields == {"height": "180"}
