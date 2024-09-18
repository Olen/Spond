#!/usr/bin/env python3

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from .base import _SpondBase

if TYPE_CHECKING:
    from datetime import datetime

    from . import JSONDict


class Spond(_SpondBase):

    DT_FORMAT = "%Y-%m-%dT00:00:00.000Z"

    _EVENT: ClassVar = "event"
    _GROUP: ClassVar = "group"

    def __init__(self, username: str, password: str) -> None:
        super().__init__(username, password, "https://api.spond.com/core/v1/")
        self.chat_url = None
        self.auth = None
        self.groups: list[JSONDict] | None = None
        self.events: list[JSONDict] | None = None
        self.messages: list[JSONDict] | None = None

    async def login_chat(self) -> None:
        api_chat_url = f"{self.api_url}chat"
        r = await self.clientsession.post(api_chat_url, headers=self.auth_headers)
        result = await r.json()
        self.chat_url = result["url"]
        self.auth = result["auth"]

    @_SpondBase.require_authentication
    async def get_groups(self) -> list[JSONDict] | None:
        """
        Retrieve all groups, subject to authenticated user's access.

        Returns
        -------
        list[JSONDict] or None
            A list of groups, each represented as a dictionary, or None if no groups
            are available.

        """
        url = f"{self.api_url}groups/"
        async with self.clientsession.get(url, headers=self.auth_headers) as r:
            self.groups = await r.json()
            return self.groups

    async def get_group(self, uid: str) -> JSONDict:
        """
        Get a group by unique ID.
        Subject to authenticated user's access.

        Parameters
        ----------
        uid : str
            UID of the group.

        Returns
        -------
        JSONDict
            Details of the group.

        Raises
        ------
        KeyError if no group is matched.

        """
        return await self._get_entity(self._GROUP, uid)

    @_SpondBase.require_authentication
    async def get_person(self, user: str) -> JSONDict:
        """
        Get a member or guardian by matching various identifiers.
        Subject to authenticated user's access.

        Parameters
        ----------
        user : str
            Identifier to match against member/guardian's id, email, full name, or
            profile id.

        Returns
        -------
        JSONDict
            Member or guardian's details.

        Raises
        ------
        KeyError if no person is matched.
        """
        if not self.groups:
            await self.get_groups()
        for group in self.groups:
            for member in group["members"]:
                if (
                    member["id"] == user
                    or ("email" in member and member["email"]) == user
                    or member["firstName"] + " " + member["lastName"] == user
                    or ("profile" in member and member["profile"]["id"] == user)
                ):
                    return member
                if "guardians" in member:
                    for guardian in member["guardians"]:
                        if (
                            guardian["id"] == user
                            or ("email" in guardian and guardian["email"]) == user
                            or guardian["firstName"] + " " + guardian["lastName"]
                            == user
                            or (
                                "profile" in guardian
                                and guardian["profile"]["id"] == user
                            )
                        ):
                            return guardian
        errmsg = f"No person matched with identifier '{user}'."
        raise KeyError(errmsg)

    @_SpondBase.require_authentication
    async def get_messages(self, max_chats: int = 100) -> list[JSONDict] | None:
        """
        Retrieve messages (chats).

        Parameters
        ----------
        max_chats : int, optional
            Set a limit on the number of chats returned.
            For performance reasons, defaults to 100.
            Uses `max` API parameter.

        Returns
        -------
        list[JSONDict] or None
            A list of chats, each represented as a dictionary, or None if no chats
            are available.

        """
        if not self.auth:
            await self.login_chat()
        url = f"{self.chat_url}/chats/"
        async with self.clientsession.get(
            url,
            headers={"auth": self.auth},
            params={"max": str(max_chats)},
        ) as r:
            self.messages = await r.json()
        return self.messages

    @_SpondBase.require_authentication
    async def _continue_chat(self, chat_id: str, text: str) -> JSONDict:
        """
        Send a given text in an existing given chat.
        Subject to authenticated user's access.

        Parameters
        ----------
        chat_id : str
            Identifier of the chat.

        text : str
            The text to be sent to the chat.

        Returns
        -------
        JSONDict
             Result of the sending.
        """
        if not self.auth:
            await self.login_chat()
        url = f"{self.chat_url}/messages"
        data = {"chatId": chat_id, "text": text, "type": "TEXT"}
        r = await self.clientsession.post(url, json=data, headers={"auth": self.auth})
        return await r.json()

    @_SpondBase.require_authentication
    async def send_message(
        self,
        text: str,
        user: str | None = None,
        group_uid: str | None = None,
        chat_id: str | None = None,
    ):
        """
        Start a new chat or continue an existing one.

        If `chat_id`of an existing chat is specified, message continues that chat.
        Otherwise, both `user` and `group_uid` must be specified, and the message starts a new chat.

        Parameters
        ----------
        text : str
            Message to send
        user : str, optional
            Identifier to match against member/guardian's id, email, full name, or
            profile id.
        group_uid : str, optional
            UID of the group.
        chat_id : str, optional
            Identifier of the chat.

        Returns
        -------
        dict
             Result of the sending.
        """
        if self.auth is None:
            await self.login_chat()

        if chat_id is not None:
            return self._continue_chat(chat_id, text)
        elif group_uid is None or user is None:
            return {
                "error": "wrong usage, group_id and user_id needed or continue chat with chat_id"
            }

        user_obj = await self.get_person(user)
        if user_obj:
            user_uid = user_obj["profile"]["id"]
        else:
            return False
        url = f"{self.chat_url}/messages"
        data = {
            "text": text,
            "type": "TEXT",
            "recipient": user_uid,
            "groupId": group_uid,
        }
        r = await self.clientsession.post(url, json=data, headers={"auth": self.auth})
        return await r.json()

    @_SpondBase.require_authentication
    async def get_events(
        self,
        group_id: str | None = None,
        subgroup_id: str | None = None,
        include_scheduled: bool = False,
        max_end: datetime | None = None,
        min_end: datetime | None = None,
        max_start: datetime | None = None,
        min_start: datetime | None = None,
        max_events: int = 100,
    ) -> list[JSONDict] | None:
        """
        Retrieve events.

        Parameters
        ----------
        group_id : str, optional
            Uses `GroupId` API parameter.
        subgroup_id : str, optional
            Uses `subgroupId` API parameter.
        include_scheduled : bool, optional
            Include scheduled events.
            (TO DO: probably events for which invites haven't been sent yet?)
            Defaults to False for performance reasons.
            Uses `scheduled` API parameter.
        max_end : datetime, optional
            Only include events which end before or at this datetime.
            Uses `maxEndTimestamp` API parameter; relates to `endTimestamp` event
            attribute.
        max_start : datetime, optional
            Only include events which start before or at this datetime.
            Uses `maxStartTimestamp` API parameter; relates to `startTimestamp` event
            attribute.
        min_end : datetime, optional
            Only include events which end after or at this datetime.
            Uses `minEndTimestamp` API parameter; relates to `endTimestamp` event
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

        """
        url = f"{self.api_url}sponds/"
        params = {
            "max": str(max_events),
            "scheduled": str(include_scheduled),
        }
        if max_end:
            params["maxEndTimestamp"] = max_end.strftime(self.DT_FORMAT)
        if max_start:
            params["maxStartTimestamp"] = max_start.strftime(self.DT_FORMAT)
        if min_end:
            params["minEndTimestamp"] = min_end.strftime(self.DT_FORMAT)
        if min_start:
            params["minStartTimestamp"] = min_start.strftime(self.DT_FORMAT)
        if group_id:
            params["groupId"] = group_id
        if subgroup_id:
            params["subgroupId"] = subgroup_id

        async with self.clientsession.get(
            url, headers=self.auth_headers, params=params
        ) as r:
            self.events = await r.json()
            return self.events

    async def get_event(self, uid: str) -> JSONDict:
        """
        Get an event by unique ID.
        Subject to authenticated user's access.

        Parameters
        ----------
        uid : str
            UID of the event.

        Returns
        -------
        JSONDict
            Details of the event.

        Raises
        ------
        KeyError if no event is matched.

        """
        return await self._get_entity(self._EVENT, uid)

    @_SpondBase.require_authentication
    async def update_event(self, uid: str, updates: JSONDict):
        """
        Updates an existing event.

        Parameters
        ----------
        uid : str
           UID of the event.
        updates : JSONDict
            The changes. e.g. if you want to change the description -> {'description': "New Description with changes"}

        Returns
        -------
        json results of post command

        """
        if not self.events:
            await self.get_events()
        for event in self.events:
            if event["id"] == uid:
                break

        url = f"{self.api_url}sponds/{uid}"

        base_event: JSONDict = {
            "heading": None,
            "description": None,
            "spondType": "EVENT",
            "startTimestamp": None,
            "endTimestamp": None,
            "commentsDisabled": False,
            "maxAccepted": 0,
            "rsvpDate": None,
            "location": {
                "id": None,
                "feature": None,
                "address": None,
                "latitude": None,
                "longitude": None,
            },
            "owners": [{"id": None}],
            "visibility": "INVITEES",
            "participantsHidden": False,
            "autoReminderType": "DISABLED",
            "autoAccept": False,
            "payment": {},
            "attachments": [],
            "id": None,
            "tasks": {
                "openTasks": [],
                "assignedTasks": [
                    {
                        "name": None,
                        "description": "",
                        "type": "ASSIGNED",
                        "id": None,
                        "adultsOnly": True,
                        "assignments": {"memberIds": [], "profiles": [], "remove": []},
                    }
                ],
            },
        }

        for key in base_event:
            if event.get(key) is not None and not updates.get(key):
                base_event[key] = event[key]
            elif updates.get(key) is not None:
                base_event[key] = updates[key]

        data = dict(base_event)
        async with self.clientsession.post(
            url, json=data, headers=self.auth_headers
        ) as r:
            self.events_update = await r.json()
            return self.events

    @_SpondBase.require_authentication
    async def get_event_attendance_xlsx(self, uid: str) -> bytes:
        """get Excel attendance report for a single event.
           Available via the web client.

        Parameters
        ----------
        uid : str
            UID of the event.

        Returns
        -------
            bytes: XLSX binary data
        """
        url = f"{self.api_url}sponds/{uid}/export"
        async with self.clientsession.get(url, headers=self.auth_headers) as r:
            output_data = await r.read()
            return output_data

    @_SpondBase.require_authentication
    async def change_response(self, uid: str, user: str, payload: JSONDict) -> JSONDict:
        """change a user's response for an event

        Parameters
        ----------
        uid : str
            UID of the event.

        user : str
            UID of the user

        payload : JSONDict
            user response to event, e.g. {"accepted": "true"}

        Returns
        -------
        JSONDict
            event["responses"] with updated info
        """
        url = f"{self.api_url}sponds/{uid}/responses/{user}"
        async with self.clientsession.put(
            url, headers=self.auth_headers, json=payload
        ) as r:
            return await r.json()

    @_SpondBase.require_authentication
    async def _get_entity(self, entity_type: str, uid: str) -> JSONDict:
        """
        Get an event or group by unique ID.

        Subject to authenticated user's access.

        Parameters
        ----------
        entity_type : str
            self._EVENT or self._GROUP.
        uid : str
            UID of the entity.

        Returns
        -------
        JSONDict
            Details of the entity.

        Raises
        ------
        KeyError if no entity is matched.
        NotImplementedError if no/unsupported entity type is specified.

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
            err_msg = f"Entity type '{entity_type}' is not supported."
            raise NotImplementedError(err_msg)

        for entity in entities:
            if entity["id"] == uid:
                return entity
        errmsg = f"No {entity_type} with id='{uid}'."
        raise KeyError(errmsg)
