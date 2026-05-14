#!/usr/bin/env python3
"""Core Spond API client.

This module contains the `Spond` class, the main entrypoint to the
[Spond](https://spond.com/) consumer API: account profile, groups, members,
events, posts, and chats. For the separate Spond Club finance API, see
`spond.club`.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, ClassVar

from . import JSONDict
from .base import _SpondBase
from .event import Event
from .group import Group
from .person import Member, Person
from .post import Post
from .profile import Profile

if TYPE_CHECKING:
    from datetime import datetime


class Spond(_SpondBase):
    """Async client for the Spond consumer API.

    Authentication happens lazily on the first API call (via the
    `require_authentication` decorator inherited from `spond.base._SpondBase`);
    you do not need to call `login()` explicitly.

    Several `get_*` methods cache their last response on the instance
    (`self.groups`, `self.events`, `self.posts`, `self.messages`,
    `self.profile`). This lets lookup helpers like `get_group(uid)` and
    `get_person(user)` avoid re-fetching when called repeatedly. To force a
    refresh, set the relevant attribute to `None` and call the `get_*` method
    again, or call the underlying `get_*s()` method directly.

    Remember to close the underlying aiohttp session when finished:

    ```python
    s = Spond(username="...", password="...")
    try:
        groups = await s.get_groups()
        ...
    finally:
        await s.clientsession.close()
    ```

    Example
    -------
    ```python
    import asyncio
    from spond import spond

    async def main():
        s = spond.Spond(username="me@example.invalid", password="secret")
        groups = await s.get_groups() or []
        for g in groups:
            print(g["name"])
        await s.clientsession.close()

    asyncio.run(main())
    ```
    """

    _API_BASE_URL: ClassVar = "https://api.spond.com/core/v1/"
    _DT_FORMAT: ClassVar = "%Y-%m-%dT00:00:00.000Z"
    _EVENT: ClassVar = "event"
    _GROUP: ClassVar = "group"

    def __init__(self, username: str, password: str) -> None:
        """Construct a Spond client.

        The credentials are stored on the instance and used to obtain an access
        token on the first authenticated call. An aiohttp `ClientSession` is
        opened immediately; close it via `await s.clientsession.close()`
        (where `s` is the constructed instance) when finished, to avoid
        `Unclosed client session` warnings.

        Parameters
        ----------
        username : str
            Spond account email address.
        password : str
            Spond account password. For accounts with 2FA enabled, login will
            currently fail — Spond's TOTP flow is not yet supported.
        """
        super().__init__(username, password, self._API_BASE_URL)
        self._chat_url = None
        self._auth = None
        self.groups: list[Group] | None = None
        self.events: list[Event] | None = None
        self.posts: list[Post] | None = None
        self.messages: list[JSONDict] | None = None
        self.profile: Profile | None = None

    async def _login_chat(self) -> None:
        """Perform the secondary handshake with Spond's chat server.

        The chat API lives on a separate host and uses its own short-lived
        token (`self._auth`) rather than the regular Bearer token used by the
        core API. This method is called lazily by `get_messages`,
        `send_message`, and `_continue_chat` on their first use; the resulting
        `self._chat_url` and `self._auth` are cached for the lifetime of the
        client.
        """
        api_chat_url = f"{self.api_url}chat"
        r = await self.clientsession.post(api_chat_url, headers=self.auth_headers)
        result = await r.json()
        self._chat_url = result["url"]
        self._auth = result["auth"]

    @_SpondBase.require_authentication
    async def get_profile(self) -> Profile:
        """Retrieve the authenticated user's profile.

        Returns a `Profile` instance with the user's account details (id,
        first/last name, email, phone, timezone, preferences). The full
        response is cached on `self.profile`.

        Returns
        -------
        Profile
            The authenticated user's profile.
        """
        url = f"{self._API_BASE_URL}profile"
        async with self.clientsession.get(url, headers=self.auth_headers) as r:
            raw = await r.json()
        self.profile = Profile.model_validate(raw)
        return self.profile

    @_SpondBase.require_authentication
    async def get_groups(self) -> list[Group] | None:
        """Retrieve every group the authenticated user is a member of.

        Each `Group` carries its `members` (typed `Member` instances, each
        with their own `guardians: list[Guardian]`), `subgroups: list[Subgroup]`,
        and `roles: list[Role]`. The full list is cached on `self.groups` and
        reused by `get_group(uid)` and `get_person(user)`.

        Returns
        -------
        list[Group] or None
            A list of groups, or `None` if the account has no groups at all.
        """
        url = f"{self.api_url}groups/"
        async with self.clientsession.get(url, headers=self.auth_headers) as r:
            raw = await r.json()
        if raw is None:
            self.groups = None
            return None
        self.groups = [Group.from_api(g, self) for g in raw]
        return self.groups

    async def get_group(self, uid: str) -> Group:
        """Look up a single group by its unique id.

        Searches the cached `self.groups` (populated by `get_groups()` on
        first call). To force a refresh, set `self.groups = None` first.

        Parameters
        ----------
        uid : str
            UID of the group.

        Returns
        -------
        Group
            The group, with members/subgroups/roles materialised as typed
            objects.

        Raises
        ------
        KeyError
            If no group with the given id is found (or the user has no groups).
        """
        return await self._get_entity(self._GROUP, uid)

    @_SpondBase.require_authentication
    async def get_person(self, user: str) -> Person:
        """Look up a member or guardian by any of several identifiers.

        Searches every member of every cached group (and each member's
        `guardians` list). The first match wins. The cache `self.groups` is
        populated by `get_groups()` if empty.

        Parameters
        ----------
        user : str
            Identifier to match against. Accepted forms:

            - the person's `uid`
            - the person's `email` (Members only — exact match)
            - first and last name joined by a single space
              (e.g. `"Ola Thoresen"`)
            - the person's `profile.id` (different from `uid` for child
              members managed by another account)

        Returns
        -------
        Person
            The first matching `Member` or `Guardian`. Use `isinstance` to
            distinguish if needed.

        Raises
        ------
        KeyError
            If no match is found across any group or guardian.
        """
        if not self.groups:
            await self.get_groups()
        for group in self.groups or []:
            for member in group.members:
                if self._match_person(member, user):
                    return member
                for guardian in member.guardians:
                    if self._match_person(guardian, user):
                        return guardian
        errmsg = f"No person matched with identifier '{user}'."
        raise KeyError(errmsg)

    @staticmethod
    def _match_person(person: Person, match_str: str) -> bool:
        """Return True if `match_str` matches any of the person's identifiers.

        Used internally by `get_person` to scan group members and guardians.
        See `get_person` for the list of accepted identifier forms.

        Parameters
        ----------
        person : Person
            A `Member` or `Guardian` from a group's `members` list (or one
            of its nested `guardians`).
        match_str : str
            The identifier to test against.

        Returns
        -------
        bool
            True on first matching identifier; False otherwise.
        """
        if person.uid == match_str:
            return True
        if person.full_name == match_str:
            return True
        if person.profile is not None and person.profile.get("id") == match_str:
            return True
        # Members have email; Guardians don't. Guard against the
        # `None == None` trap — if the member has no email on record and
        # the caller (somehow) supplied None as match_str, we don't want
        # to claim a match.
        return (
            isinstance(person, Member)
            and bool(person.email)
            and person.email == match_str
        )

    @_SpondBase.require_authentication
    async def get_posts(
        self,
        group_id: str | None = None,
        max_posts: int = 20,
        include_comments: bool = True,
    ) -> list[Post] | None:
        """Retrieve posts from group walls.

        Posts are announcements/messages posted to group walls, as opposed to
        chat messages or events.

        Parameters
        ----------
        group_id : str, optional
            Filter by group. Uses `groupId` API parameter.
        max_posts : int, optional
            Set a limit on the number of posts returned.
            For performance reasons, defaults to 20.
            Uses `max` API parameter.
        include_comments : bool, optional
            Include comments on posts.
            Defaults to True.
            Uses `includeComments` API parameter.

        Returns
        -------
        list[Post] or None
            A list of posts, or `None` if the account has no posts.

        Raises
        ------
        ValueError
            Raised when the request to the API fails.
        """
        url = f"{self.api_url}posts/"
        params: dict[str, str] = {
            "type": "PLAIN",
            "max": str(max_posts),
            "includeComments": str(include_comments).lower(),
        }
        if group_id:
            params["groupId"] = group_id

        async with self.clientsession.get(
            url, headers=self.auth_headers, params=params
        ) as r:
            if not r.ok:
                error_details = await r.text()
                raise ValueError(
                    f"Request failed with status {r.status}: {error_details}"
                )
            raw = await r.json()
        if raw is None:
            self.posts = None
            return None
        self.posts = [Post.model_validate(p) for p in raw]
        return self.posts

    @_SpondBase.require_authentication
    async def get_messages(self, max_chats: int = 100) -> list[JSONDict] | None:
        """Retrieve recent chats (one-to-one and group conversations).

        "Chats" here refers to the in-app direct/group messaging feature, not
        comments on events or posts. Uses Spond's separate chat-server host
        and chat token (handled internally by `_login_chat`).

        The full response is cached on `self.messages`.

        Parameters
        ----------
        max_chats : int, optional
            Maximum number of chats to return. Defaults to 100 for performance.
            Uses the `max` API parameter.

        Returns
        -------
        list[JSONDict] or None
            A list of chat objects ordered by most recent activity. `None` if
            the account has no chats.
        """
        if not self._auth:
            await self._login_chat()
        url = f"{self._chat_url}/chats/"
        async with self.clientsession.get(
            url,
            headers={"auth": self._auth},
            params={"max": str(max_chats)},
        ) as r:
            self.messages = await r.json()
        return self.messages

    @_SpondBase.require_authentication
    async def _continue_chat(self, chat_id: str, text: str) -> JSONDict:
        """Append a text message to an existing chat thread.

        Internal helper used by `send_message` when called with `chat_id`.
        Performs the lazy chat-server login (`_login_chat`) on first use.

        Parameters
        ----------
        chat_id : str
            Identifier of the existing chat to continue.
        text : str
            Message body to send.

        Returns
        -------
        JSONDict
            The Spond API response for the send operation.
        """
        if not self._auth:
            await self._login_chat()
        url = f"{self._chat_url}/messages"
        data = {"chatId": chat_id, "text": text, "type": "TEXT"}
        r = await self.clientsession.post(url, json=data, headers={"auth": self._auth})
        return await r.json()

    @_SpondBase.require_authentication
    async def send_message(
        self,
        text: str,
        user: str | None = None,
        group_uid: str | None = None,
        chat_id: str | None = None,
    ) -> JSONDict:
        """Send a chat message, either continuing an existing thread or
        starting a new one.

        Two calling patterns:

        - **Continue an existing chat**: pass `chat_id` (the recipient and
          group context are inferred from the existing thread). `user` and
          `group_uid` are ignored.
        - **Start a new chat**: pass both `user` (the recipient) and
          `group_uid` (the group context the chat belongs to). The user is
          resolved via `get_person()` to find the underlying profile id.

        Parameters
        ----------
        text : str
            Message body to send.
        user : str, optional
            Recipient identifier when starting a new chat. Accepts the same
            forms as `get_person()`: member id, email, full name, or
            profile id. Required when `chat_id` is not given.
        group_uid : str, optional
            UID of the group that scopes the new chat. Required when `chat_id`
            is not given.
        chat_id : str, optional
            Identifier of an existing chat to continue. When provided,
            `user` and `group_uid` are not consulted.

        Returns
        -------
        JSONDict
            The Spond API response for the send operation.

        Raises
        ------
        ValueError
            Neither `chat_id` nor both of `user`/`group_uid` were supplied —
            the call has no way to identify the target chat.
        KeyError
            `user` was given but doesn't match any member or guardian in any
            of the authenticated user's groups (propagated from
            `get_person`).
        """
        if self._auth is None:
            await self._login_chat()

        if chat_id is not None:
            return await self._continue_chat(chat_id, text)
        if group_uid is None or user is None:
            raise ValueError(
                "send_message requires either chat_id (to continue an existing "
                "chat) or both user and group_uid (to start a new one)."
            )

        user_obj = await self.get_person(user)
        if user_obj.profile is None or "id" not in user_obj.profile:
            raise ValueError(
                f"Person {user_obj.uid} has no profile id; Spond cannot route "
                f"a message without one."
            )
        user_uid = user_obj.profile["id"]
        url = f"{self._chat_url}/messages"
        data = {
            "text": text,
            "type": "TEXT",
            "recipient": user_uid,
            "groupId": group_uid,
        }
        r = await self.clientsession.post(url, json=data, headers={"auth": self._auth})
        return await r.json()

    @_SpondBase.require_authentication
    async def get_events(
        self,
        group_id: str | None = None,
        subgroup_id: str | None = None,
        include_scheduled: bool = False,
        include_hidden: bool = False,
        max_end: datetime | None = None,
        min_end: datetime | None = None,
        max_start: datetime | None = None,
        min_start: datetime | None = None,
        max_events: int = 100,
    ) -> list[Event] | None:
        """Retrieve events visible to the authenticated user.

        Filters can narrow by group/subgroup, by start/end timestamp window,
        and by visibility (scheduled, hidden). The full response is cached on
        `self.events`.

        Note: `get_event(uid)` looks up events via this method's cache, so
        it inherits these defaults — an event that doesn't appear in the
        first `max_events` results or is excluded by `include_scheduled=False`
        is unreachable through `get_event()`. If you need broader visibility,
        call this method directly with appropriate filters.

        Parameters
        ----------
        group_id : str, optional
            Restrict to events belonging to this group. Uses `groupId` API
            parameter.
        subgroup_id : str, optional
            Restrict to events within this subgroup. Uses `subGroupId` API
            parameter.
        include_scheduled : bool, optional
            Include scheduled events (events whose invitations are queued to be
            sent in the future).
            Defaults to False for performance reasons.
            Uses `scheduled` API parameter.
        include_hidden : bool, optional
            Include hidden events.
            Uses `includeHidden` API parameter.
            'includeHidden' filter is only available inside a group.
        max_end : datetime, optional
            Only include events which end before or at this datetime.
            Uses `maxEndTimestamp` API parameter; relates to `endTimestamp` event
            attribute.
        min_end : datetime, optional
            Only include events which end after or at this datetime.
            Uses `minEndTimestamp` API parameter; relates to `endTimestamp` event
            attribute.
        max_start : datetime, optional
            Only include events which start before or at this datetime.
            Uses `maxStartTimestamp` API parameter; relates to `startTimestamp` event
            attribute.
        min_start : datetime, optional
            Only include events which start after or at this datetime.
            Uses `minStartTimestamp` API parameter; relates to `startTimestamp` event
            attribute.
        max_events : int, optional
            Set a limit on the number of events returned.
            For performance reasons, defaults to 100.
            Uses `max` API parameter.

        Returns
        -------
        list[Event] or None
            A list of `Event` instances, or `None` if no events match.

        Raises
        ------
        ValueError
            Raised when the request to the API fails. This occurs if the response
            status code indicates an error (e.g., 4xx or 5xx). The error message
            includes the HTTP status code and the response body for debugging purposes.
        """
        url = f"{self.api_url}sponds/"
        params = {
            "max": str(max_events),
            "scheduled": str(include_scheduled),
        }
        if max_end:
            params["maxEndTimestamp"] = max_end.strftime(self._DT_FORMAT)
        if max_start:
            params["maxStartTimestamp"] = max_start.strftime(self._DT_FORMAT)
        if min_end:
            params["minEndTimestamp"] = min_end.strftime(self._DT_FORMAT)
        if min_start:
            params["minStartTimestamp"] = min_start.strftime(self._DT_FORMAT)
        if group_id:
            params["groupId"] = group_id
        if subgroup_id:
            params["subGroupId"] = subgroup_id
        if include_hidden:
            params["includeHidden"] = "true"

        async with self.clientsession.get(
            url, headers=self.auth_headers, params=params
        ) as r:
            if not r.ok:
                error_details = await r.text()
                raise ValueError(
                    f"Request failed with status {r.status}: {error_details}"
                )
            raw = await r.json()
        if raw is None:
            self.events = None
            return None
        self.events = [Event.from_api(e, self) for e in raw]
        return self.events

    async def get_event(self, uid: str) -> Event:
        """Look up a single event by its unique id.

        Routes through the cached events list (populated by `get_events()`),
        which means events outside the `max_events=100` default or those
        excluded by `include_scheduled=False` may not be findable. To reach
        those events, call `get_events()` directly with appropriate filters
        first to populate the cache, then call this method.

        Parameters
        ----------
        uid : str
            UID of the event.

        Returns
        -------
        Event
            The matching event.

        Raises
        ------
        KeyError
            If no event with the given id is found in the cache.
        """
        return await self._get_entity(self._EVENT, uid)

    @_SpondBase.require_authentication
    async def update_event(self, uid: str, updates: JSONDict) -> JSONDict:
        """Deprecated — use `Event.update()` on the typed object instead.

        ```python
        # Old:
        await spond.update_event(uid, {"description": "..."})

        # New:
        event = await spond.get_event(uid)
        await event.update(description="...")
        ```

        Delegates to `Event.update()`; unknown keys in `updates` pass through
        to Spond verbatim (Spond decides what it accepts, the SDK doesn't
        gate). Returns the updated event as a dict for shape parity with the
        pre-OO API. Emits `DeprecationWarning`.
        """
        warnings.warn(
            "Spond.update_event() is deprecated; use Event.update() on the "
            "object returned by Spond.get_event() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        event = await self.get_event(uid)
        # Pass as positional dict, not **kwargs — `updates` may contain keys
        # like `self` or `cls` that would clash with bound-method calling.
        new_event = await event.update(updates)
        return new_event.model_dump(by_alias=True, mode="json")

    @_SpondBase.require_authentication
    async def get_event_attendance_xlsx(self, uid: str) -> bytes:
        """Deprecated — use `Event.attendance_xlsx()` on the typed object instead.

        ```python
        # Old:
        data = await spond.get_event_attendance_xlsx(uid)

        # New:
        event = await spond.get_event(uid)
        data = await event.attendance_xlsx()
        ```

        Kept as a thin pass-through for backward compatibility. Emits
        `DeprecationWarning`.
        """
        warnings.warn(
            "Spond.get_event_attendance_xlsx() is deprecated; use "
            "Event.attendance_xlsx() on the object returned by "
            "Spond.get_event() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        url = f"{self.api_url}sponds/{uid}/export"
        async with self.clientsession.get(url, headers=self.auth_headers) as r:
            return await r.read()

    @_SpondBase.require_authentication
    async def change_response(self, uid: str, user: str, payload: JSONDict) -> JSONDict:
        """Deprecated — use `Event.change_response()` on the typed object instead.

        ```python
        # Old:
        await spond.change_response(uid, member_uid, {"accepted": "true"})

        # New:
        event = await spond.get_event(uid)
        await event.change_response(member_uid, accepted=True)
        ```

        Kept as a **thin pass-through** for backward compatibility: forwards
        `payload` verbatim to the API. Any extra keys the caller supplies
        (beyond `accepted` / `declineMessage`) reach the server unchanged,
        matching the old semantics. Emits `DeprecationWarning`.
        """
        warnings.warn(
            "Spond.change_response() is deprecated; use Event.change_response() "
            "on the object returned by Spond.get_event() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        url = f"{self.api_url}sponds/{uid}/responses/{user}"
        async with self.clientsession.put(
            url, headers=self.auth_headers, json=payload
        ) as r:
            return await r.json()

    @_SpondBase.require_authentication
    async def _get_entity(self, entity_type: str, uid: str) -> JSONDict:
        """Internal lookup helper shared by `get_event` and `get_group`.

        Routes to the relevant cache (`self.events` or `self.groups`),
        triggers a fetch via `get_events()` / `get_groups()` if the cache is
        empty, then linearly scans for a matching `id`. Raises `KeyError`
        cleanly (rather than `TypeError`) when the cache remains empty after
        the fetch attempt — the underlying `get_*s()` method may legitimately
        return `None` if the account has no events/groups available.

        Parameters
        ----------
        entity_type : str
            One of `self._EVENT` (`"event"`) or `self._GROUP` (`"group"`).
        uid : str
            UID of the entity to find.

        Returns
        -------
        JSONDict
            The matching entity dict.

        Raises
        ------
        KeyError
            No entity with that id was found (either because the relevant
            cache is empty or because the id doesn't appear in it).
        NotImplementedError
            `entity_type` is something other than `"event"` or `"group"`.
        """
        if entity_type == self._EVENT:
            if not self.events:
                await self.get_events()
            entities = self.events
        elif entity_type == self._GROUP:
            if not self.groups:
                await self.get_groups()
            entities = self.groups
        else:
            errmsg = f"Entity type '{entity_type}' is not supported."
            raise NotImplementedError(errmsg)

        errmsg = f"No {entity_type} with id='{uid}'."
        if not entities:
            raise KeyError(errmsg)

        for entity in entities:
            if entity.uid == uid:
                return entity
        raise KeyError(errmsg)
