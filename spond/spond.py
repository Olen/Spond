#!/usr/bin/env python3
"""Core Spond API client.

This module contains the `Spond` class, the main entrypoint to the
[Spond](https://spond.com/) consumer API: account profile, groups, members,
events, posts, and chats. For the separate Spond Club finance API, see
`spond.club`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from . import JSONDict
from ._event_template import _EVENT_TEMPLATE
from .base import _SpondBase

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
    _EVENT_TEMPLATE: ClassVar = _EVENT_TEMPLATE
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
            currently fail — see #205.
        """
        super().__init__(username, password, self._API_BASE_URL)
        self._chat_url = None
        self._auth = None
        self.groups: list[JSONDict] | None = None
        self.events: list[JSONDict] | None = None
        self.posts: list[JSONDict] | None = None
        self.messages: list[JSONDict] | None = None
        self.profile: JSONDict | None = None

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
    async def get_profile(self) -> JSONDict:
        """Retrieve the authenticated user's profile.

        The profile dict includes at least the user's `id`, `firstName`, and
        `lastName`, plus contact details and account preferences. The full
        response is cached on `self.profile`.

        Returns
        -------
        JSONDict
            The profile object as returned by the Spond API.
        """
        url = f"{self._API_BASE_URL}profile"
        async with self.clientsession.get(url, headers=self.auth_headers) as r:
            self.profile = await r.json()
            return self.profile

    @_SpondBase.require_authentication
    async def get_groups(self) -> list[JSONDict] | None:
        """Retrieve every group the authenticated user is a member of.

        Each group dict includes a `members` list, with each member dict
        containing `id`, `firstName`, `lastName`, and (for child profiles
        managed by another account) a nested `guardians` list of the same
        shape. The full response is cached on `self.groups` and reused by
        `get_group(uid)` and `get_person(user)`.

        Returns
        -------
        list[JSONDict] or None
            A list of groups, each represented as a dictionary. `None` if the
            account has no groups at all.
        """
        url = f"{self.api_url}groups/"
        async with self.clientsession.get(url, headers=self.auth_headers) as r:
            self.groups = await r.json()
            return self.groups

    async def get_group(self, uid: str) -> JSONDict:
        """Look up a single group by its unique id.

        Searches the cached `self.groups` (populated by `get_groups()` on
        first call). To force a refresh, set `self.groups = None` first.

        Parameters
        ----------
        uid : str
            UID of the group.

        Returns
        -------
        JSONDict
            The group's details, with the same shape as elements returned by
            `get_groups()`.

        Raises
        ------
        KeyError
            If no group with the given id is found (or the user has no groups).
        """
        return await self._get_entity(self._GROUP, uid)

    @_SpondBase.require_authentication
    async def get_person(self, user: str) -> JSONDict:
        """Look up a member or guardian by any of several identifiers.

        Searches every member of every cached group (and each member's
        `guardians` list). The first match wins. The cache `self.groups` is
        populated by `get_groups()` if empty.

        Parameters
        ----------
        user : str
            Identifier to match against. Accepted forms:

            - the member's `id`
            - the member's email (exact match)
            - first and last name joined by a single space
              (e.g. `"Ola Thoresen"`)
            - the member's `profile.id` (different from `id` for child profiles)

        Returns
        -------
        JSONDict
            The first matching member or guardian dict. Shape matches the
            entries in a group's `members` list from `get_groups()`.

        Raises
        ------
        KeyError
            If no match is found across any group or guardian.
        """
        if not self.groups:
            await self.get_groups()
        for group in self.groups:
            for member in group["members"]:
                if self._match_person(member, user):
                    return member
                if "guardians" in member:
                    for guardian in member["guardians"]:
                        if self._match_person(guardian, user):
                            return guardian
        errmsg = f"No person matched with identifier '{user}'."
        raise KeyError(errmsg)

    @staticmethod
    def _match_person(person: JSONDict, match_str: str) -> bool:
        """Return True if `match_str` matches any of the person's identifiers.

        Used internally by `get_person` to scan group members and guardians.
        See `get_person` for the list of accepted identifier forms.

        Parameters
        ----------
        person : JSONDict
            A member or guardian dict from a group's `members` list.
        match_str : str
            The identifier to test against.

        Returns
        -------
        bool
            True on first matching identifier; False otherwise.
        """
        return (
            person["id"] == match_str
            or ("email" in person and person["email"]) == match_str
            or person["firstName"] + " " + person["lastName"] == match_str
            or ("profile" in person and person["profile"]["id"] == match_str)
        )

    @_SpondBase.require_authentication
    async def get_posts(
        self,
        group_id: str | None = None,
        max_posts: int = 20,
        include_comments: bool = True,
    ) -> list[JSONDict] | None:
        """
        Retrieve posts from group walls.

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
        list[JSONDict] or None
            A list of posts, each represented as a dictionary, or None if no
            posts are available.

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
            self.posts = await r.json()
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
        user_uid = user_obj["profile"]["id"]
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
    ) -> list[JSONDict] | None:
        """Retrieve events visible to the authenticated user.

        Filters can narrow by group/subgroup, by start/end timestamp window,
        and by visibility (scheduled, hidden). The full response is cached on
        `self.events`.

        Note: `get_event(uid)` is a wrapper around this method via the cache,
        so it inherits these defaults — an event that doesn't appear in the
        first `max_events` results or is excluded by `include_scheduled=False`
        is unreachable through `get_event()` on current main. PR #236 changes
        `get_event()` to fetch the singular `sponds/{uid}` endpoint directly,
        removing that coupling; until it lands, pass appropriate filters here
        when you need broader visibility.

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
        list[JSONDict] or None
             A list of events, each represented as a dictionary, or None if no events
             are available.

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
            self.events = await r.json()
            return self.events

    async def get_event(self, uid: str) -> JSONDict:
        """Look up a single event by its unique id.

        Currently routes through the cached events list (populated by
        `get_events()`). Note this means events outside the `max_events=100`
        default or with `scheduled=true` may not be findable — see #137 and
        #138 (fix in PR #236 routes this through the singular `sponds/{uid}`
        endpoint instead).

        Parameters
        ----------
        uid : str
            UID of the event.

        Returns
        -------
        JSONDict
            The event's details, with the same shape as elements returned by
            `get_events()`.

        Raises
        ------
        KeyError
            If no event with the given id is found in the cache.
        """
        return await self._get_entity(self._EVENT, uid)

    @_SpondBase.require_authentication
    async def update_event(self, uid: str, updates: JSONDict) -> JSONDict:
        """Update an existing event by merging changes into the current state.

        The implementation fetches the event via `_get_entity()`, copies the
        fields present in `_EVENT_TEMPLATE` from the existing event as the
        base, then overlays any keys provided in `updates`. The merged event
        is POSTed back to `sponds/{uid}`.

        Parameters
        ----------
        uid : str
            UID of the event to update.
        updates : JSONDict
            Mapping of keys to new values. Only keys present in
            `_EVENT_TEMPLATE` are honoured. Example:

            ```python
            await s.update_event(uid, {"description": "New description"})
            ```

        Returns
        -------
        JSONDict
            The Spond API response from the POST — the updated event as
            persisted server-side.
        """
        event = await self._get_entity(self._EVENT, uid)
        url = f"{self.api_url}sponds/{uid}"

        base_event = self._EVENT_TEMPLATE.copy()
        for key in base_event:
            if event.get(key) is not None and not updates.get(key):
                base_event[key] = event[key]
            elif updates.get(key) is not None:
                base_event[key] = updates[key]

        async with self.clientsession.post(
            url, json=base_event, headers=self.auth_headers
        ) as r:
            return await r.json()

    @_SpondBase.require_authentication
    async def get_event_attendance_xlsx(self, uid: str) -> bytes:
        """Download the attendance report for an event as XLSX bytes.

        Thin wrapper around Spond's own "Export attendance history" feature
        in the web UI. The columns and format are determined by Spond, not by
        this library — for example, the export does not include member ids
        (see closed issue #227). For a customisable CSV alternative built
        from `get_event()` data, see `examples/attendance.py`.

        Parameters
        ----------
        uid : str
            UID of the event whose attendance report to fetch.

        Returns
        -------
        bytes
            Raw XLSX file contents. Typically written directly to disk:

            ```python
            import pathlib

            data = await s.get_event_attendance_xlsx(uid)
            pathlib.Path(f"{uid}.xlsx").write_bytes(data)
            ```
        """
        url = f"{self.api_url}sponds/{uid}/export"
        async with self.clientsession.get(url, headers=self.auth_headers) as r:
            return await r.read()

    @_SpondBase.require_authentication
    async def change_response(self, uid: str, user: str, payload: JSONDict) -> JSONDict:
        """Update a single member's response (accept/decline) for an event.

        Useful for managing attendance on someone else's behalf (e.g. a coach
        accepting on behalf of a player who can't reach the app). The caller
        must have permission on the event.

        Parameters
        ----------
        uid : str
            UID of the event.
        user : str
            UID of the member whose response to change. Note: this is the
            *member's* id (as seen in `group["members"][i]["id"]`), not the
            authenticated user's id.
        payload : JSONDict
            The response body. Common shapes:

            - `{"accepted": "true"}` — accept the invitation
            - `{"accepted": "false"}` — decline (Spond may also accept a
              `"declineMessage"` field with a reason)

        Returns
        -------
        JSONDict
            The event's `responses` object with the updated id lists
            (`acceptedIds`, `declinedIds`, `unansweredIds`, etc.).
        """
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
        empty, then linearly scans for a matching `id`. The empty-cache case
        is handled explicitly to avoid the `TypeError: 'NoneType' object is
        not iterable` that previously occurred (see #136, fixed in #235).

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
            # Direct fetch by uid, so this is not constrained by
            # `get_events()`'s default `max_events` cap or its
            # `include_scheduled=False` filter.
            return await self._fetch_event_by_uid(uid)
        if entity_type == self._GROUP:
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
            if entity["id"] == uid:
                return entity
        raise KeyError(errmsg)

    async def _fetch_event_by_uid(self, uid: str) -> JSONDict:
        """Fetch a single event from the singular endpoint.

        `includeComments=true` makes the response shape match a list-endpoint
        element (the singular endpoint otherwise omits the `comments` field).
        """
        url = f"{self.api_url}sponds/{uid}"
        params = {"includeComments": "true"}
        async with self.clientsession.get(
            url, headers=self.auth_headers, params=params
        ) as r:
            if r.status == 404:
                raise KeyError(f"No event with id='{uid}'.")
            if not r.ok:
                error_details = await r.text()
                raise ValueError(
                    f"Request failed with status {r.status}: {error_details}"
                )
            return await r.json()
