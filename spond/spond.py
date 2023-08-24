#!/usr/bin/env python3

from datetime import datetime
from typing import List, Optional

import aiohttp


class Spond:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.api_url = "https://api.spond.com/core/v1/"
        self.clientsession = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
        self.chat_url = None
        self.auth = None
        self.token = None
        self.groups = None
        self.events = None

    @property
    def auth_headers(self):
        return {
            "content-type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "auth": f"{self.auth}",
        }

    async def login(self):
        login_url = f"{self.api_url}login"
        data = {"email": self.username, "password": self.password}
        async with self.clientsession.post(login_url, json=data) as r:
            login_result = await r.json()
            self.token = login_result["loginToken"]

        api_chat_url = f"{self.api_url}chat"
        headers = {
            "content-type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        r = await self.clientsession.post(api_chat_url, headers=headers)
        result = await r.json()
        self.chat_url = result["url"]
        self.auth = result["auth"]

    async def get_groups(self):
        """
        Get all groups.
        Subject to authenticated user's access.

        Returns
        -------
        list of dict
            Groups; each group is a dict.
        """
        if not self.token:
            await self.login()
        url = f"{self.api_url}groups/"
        async with self.clientsession.get(url, headers=self.auth_headers) as r:
            self.groups = await r.json()
            return self.groups

    async def get_group(self, uid) -> dict:
        """
        Get a group by unique ID.
        Subject to authenticated user's access.

        Parameters
        ----------
        uid : str
            UID of the group.

        Returns
        -------
        Details of the group.
        """
        if not self.token:
            await self.login()
        if not self.groups:
            await self.get_groups()
        for group in self.groups:
            if group["id"] == uid:
                return group
        raise IndexError

    async def get_person(self, user) -> dict:
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
        Member or guardian's details.
        """
        if not self.token:
            await self.login()
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
        raise IndexError

    async def get_messages(self):
        if not self.token:
            await self.login()
        url = f"{self.chat_url}/chats/?max=10"
        headers = {"auth": self.auth}
        async with self.clientsession.get(url, headers=headers) as r:
            return await r.json()

    async def _continue_chat(self, chat_id, text):
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
        dict
             Result of the sending.
        """
        if not self.token:
            await self.login()
        url = f"{self.chat_url}/messages"
        data = {"chatId": chat_id, "text": text, "type": "TEXT"}
        headers = {"auth": self.auth}
        r = await self.clientsession.post(url, json=data, headers=headers)
        return await r.json()

    async def send_message(self, text, user=None, group_uid=None, chat_id=None):
        """
        Starts a new chat or continue old one.

        Parameters
        ----------
        text: str
            Message to send
        user : str
            Identifier to match against member/guardian's id, email, full name, or
            profile id.
        group_uid : str
            UID of the group.
        chat_id : str
            Identifier of the chat.

        Returns
        -------
        dict
             Result of the sending.
        """

        if chat_id is not None:
            return self._continue_chat(chat_id, text)
        elif group_uid is None or user is None:
            return {
                "error": "wrong usage, group_id and user_id needed or continue chat with chat_id"
            }

        if not self.token:
            await self.login()
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
        headers = {"auth": self.auth}
        r = await self.clientsession.post(url, json=data, headers=headers)
        return await r.json()

    async def get_events(
        self,
        group_id: Optional[str] = None,
        include_scheduled: bool = False,
        max_end: Optional[datetime] = None,
        min_end: Optional[datetime] = None,
        max_start: Optional[datetime] = None,
        min_start: Optional[datetime] = None,
        max_events: int = 100,
    ) -> List[dict]:
        """
        Get events.
        Subject to authenticated user's access.

        Parameters
        ----------
        group_id : str, optional
            Uses `GroupId` API parameter.
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
        list of dict
            Events; each event is a dict.
        """
        if not self.token:
            await self.login()
        url = (
            f"{self.api_url}sponds/?"
            f"max={max_events}"
            f"&scheduled={include_scheduled}"
        )
        if max_end:
            url += f"&maxEndTimestamp={max_end.strftime('%Y-%m-%dT00:00:00.000Z')}"
        if max_start:
            url += f"&maxStartTimestamp={max_start.strftime('%Y-%m-%dT00:00:00.000Z')}"
        if min_end:
            url += f"&minEndTimestamp={min_end.strftime('%Y-%m-%dT00:00:00.000Z')}"
        if min_start:
            url += f"&minStartTimestamp={min_start.strftime('%Y-%m-%dT00:00:00.000Z')}"
        if group_id:
            url += f"&groupId={group_id}"

        async with self.clientsession.get(url) as r:
            self.events = await r.json()
            return self.events

    async def get_event(self, uid) -> dict:
        """
        Get an event by unique ID.
        Subject to authenticated user's access.

        Parameters
        ----------
        uid : str
            UID of the event.

        Returns
        -------
        Details of the event.
        """
        if not self.token:
            await self.login()
        if not self.events:
            await self.get_events()
        for event in self.events:
            if event["id"] == uid:
                return event
        raise IndexError

    async def update_event(self, uid, updates: dict):
        """
        Updates an existing event.

        Parameters:
        ----------
        uid : str
           UID of the event.
        updates : dict
            The changes. e.g. if you want to change the description -> {'description': "New Description with changes"}

        Returns:
        ----------
        json results of post command

        """
        if not self.token:
            await self.login()
        if not self.events:
            await self.get_events()
        for event in self.events:
            if event["id"] == uid:
                break

        url = f"{self.api_url}sponds/{uid}"

        base_event = {
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
            if event.get(key) != None and not updates.get(key):
                base_event[key] = event[key]
            elif updates.get(key) != None:
                base_event[key] = updates[key]

        data = dict(base_event)
        headers = {"content-type": "application/json;charset=utf-8"}
        async with self.clientsession.post(url, json=data, headers=headers) as r:
            self.events_update = await r.json()
            return self.events
