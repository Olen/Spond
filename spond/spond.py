#!/usr/bin/env python3

from datetime import datetime
from typing import List

import aiohttp


class Spond:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.apiurl = "https://spond.com/api/2.1/"
        self.clientsession = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
        self.chaturl = None
        self.auth = None
        self.cookie = None
        self.groups = None
        self.events = None

    async def login(self):
        url = self.apiurl + "login"
        data = {"email": self.username, "password": self.password}
        async with self.clientsession.post(url, json=data) as r:
            self.cookie = r.cookies["auth"]
        url = self.apiurl + "chat"
        headers = {"content-type": "application/json;charset=utf-8"}
        res = await self.clientsession.post(url, headers=headers)
        result = await res.json()

        self.chaturl = result["url"]
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
        if not self.cookie:
            await self.login()
        url = self.apiurl + "groups/"
        async with self.clientsession.get(url) as r:
            self.groups = await r.json()
            return self.groups

    async def get_group(self, uid):
        """
        Get a group by unique ID.
        Subject to authenticated user's access.

        Parameters
        ----------
        uid : str
            UID of the group.

        Returns
        -------
        dict
            Details of the group.
        """
        if not self.cookie:
            await self.login()
        if not self.groups:
            await self.get_groups()
        for group in self.groups:
            if group["id"] == uid:
                return group

    async def get_person(self, user):
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
        dict
             Member or guardian's details.
        """
        if not self.cookie:
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

    async def get_messages(self):
        if not self.cookie:
            await self.login()
        url = self.chaturl + "/chats/?max=10"
        headers = {"auth": self.auth}
        async with self.clientsession.get(url, headers=headers) as r:
            return await r.json()

    async def send_message(self, chat_id, text):
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
        if not self.cookie:
            await self.login()
        url = self.chaturl + "/messages"
        data = {"chatId": chat_id, "text": text, "type": "TEXT"}
        headers = {"auth": self.auth}
        r = await self.clientsession.post(url, json=data, headers=headers)
        return await r.json()

    async def get_events(
        self,
        group_id: str = None,
        include_scheduled: bool = False,
        max_end: datetime = None,
        min_end: datetime = None,
        max_start: datetime = None,
        min_start: datetime = None,
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
        if not self.cookie:
            await self.login()
        url = (
            f"{self.apiurl}sponds/?"
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

    async def get_event(self, uid):
        """
        Get an event by unique ID.
        Subject to authenticated user's access.

        Parameters
        ----------
        uid : str
            UID of the event.

        Returns
        -------
        dict
            Details of the event.
        """
        if not self.cookie:
            await self.login()
        if not self.events:
            await self.get_events()
        for event in self.events:
            if event["id"] == uid:
                return event

    async def write_post(self, group_id: str, title: str, body: str,
                         comment_disabled: bool) -> Dict[str, Any]:
        """
        Write post on the main page of a group.

        Parameters
        ----------
        group_id : str
            Id of the group.
        title: str
            Title of the post.
        body: str
            Body of the post.
        comment_disabled: bool
            Bool to say if the comments on the post are disabled or not.

        Returns
        -------
        dict
            Result of writing the post.
        """
        if not self.cookie:
            await self.login()
        url = self.apiurl + "posts"

        data = {
            "type": "PLAIN",
            "groupId": group_id,
            "visibility": "ALL",
            "commentsDisabled": comment_disabled,
            "attachments": [],
            "title": title,
            "body": body,
            "media": []
        }

        headers = {'auth': self.auth}
        r = await self.clientsession.post(url, json=data, headers=headers)
        return await r.json()

    async def write_poll(self, group_id: str, title: str, description: str,
                         comment_disabled: bool, options: List[str],
                         hide_votes: bool, multiple_choices: bool, due_datetime: datetime) -> Dict[str, Any]:
        """
        Write poll on the main page of a group.

        Parameters
        ----------
        group_id : str
            Id of the group.
        title: str
            Title of the poll.
        description: str
            Description of the poll.
        comment_disabled: bool
            Bool to say if the comments on the poll are disabled or not.
        options: list
            List of options.
        hide_votes: bool
            Bool to say if the votes are hided or not.
        multiple_choices: bool
            Bool to say if multiple choices are allowed or not.
        due_datetime: datetime
            Deadline to complete the poll.

        Returns
        -------
        dict
            Result of writing the poll.
        """
        if not self.cookie:
            await self.login()
        url = self.apiurl + "posts"

        data = {
            "type": "POLL",
            "groupId": group_id,
            "visibility": "ALL",
            "commentsDisabled": comment_disabled,
            "attachments": [],
            "poll": {
                "question": title,
                "description": description,
                "options": [{"text": option} for option in options],
                "hideVotes": hide_votes,
                "dueBy": due_datetime.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                "multipleChoice": multiple_choices,
                "commentsDisabled": comment_disabled,
                "type": "TEXT"
            }
        }

        headers = {'auth': self.auth}
        r = await self.clientsession.post(url, json=data, headers=headers)
        return await r.json()
