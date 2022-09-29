#!/usr/bin/env python3

from typing import List
import aiohttp

class Spond():
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
        data = { 'email': self.username, 'password': self.password }
        async with self.clientsession.post(url, json=data) as r:
            self.cookie = r.cookies['auth']
        # print(self.cookie.value)
        url = self.apiurl + "chat"
        # headers = { 'content-length': '0', 'accept': '*/*', 'api-level': '2.5.25', 'origin': 'https://spond.com', 'referer': 'https://spond.com/client/', 'content-type': 'application/json;charset=utf-8' }
        headers = { 'content-type': 'application/json;charset=utf-8' }
        res = await self.clientsession.post(url, headers=headers)
        result = await res.json()

        self.chaturl = result['url']
        self.auth = result['auth']

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
            if group['id'] == uid:
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
            for member in group['members']:
                if member['id'] == user or ('email' in member and member['email']) == user or member['firstName'] + " " + member['lastName'] == user or ( 'profile' in member and member['profile']['id'] == user):
                    return member
                if 'guardians' in member:
                    for guardian in member['guardians']:
                        if guardian['id'] == user or ('email' in guardian and guardian['email']) == user or guardian['firstName'] + " " + guardian['lastName'] == user or ( 'profile' in guardian and guardian['profile']['id'] == user):
                            return guardian

    async def get_messages(self):
        if not self.cookie:
            await self.login()
        url = self.chaturl + "/chats/?max=10"
        headers = { 'auth': self.auth }
        async with self.clientsession.get(url, headers=headers) as r:
            return await r.json()


    async def send_message(self, recipient, text):
        if not self.cookie:
            await self.login()
        url = self.chaturl + "/messages"
        data = { 'recipient': recipient, 'text': text, 'type': "TEXT" }
        headers = { 'auth': self.auth }
        r = await self.clientsession.post(url, json=data, headers=headers)
        print(r)
        return await r.json()

    async def get_events(
        self,
        max_end=None,
        min_end=None,
        group_id=None,
        max_events=100,
    ) -> List[dict]:
        """
        Get events.
        Subject to authenticated user's access.

        Parameters
        ----------
        max_end : datetime, optional
            Include only events which end before or at this datetime.
            Defaults to 100 for performance reasons.
            Uses `maxEndTimestamp` API parameter.
        min_end : datetime, optional
            Include only events which end after or at this datetime.
            Uses `minEndTimestamp` API parameter.
        group_id : str, optional
            Include only events which finish after this value.
            Uses `GroupId` API parameter.
        max_events : int, optional
            Set a limit on the number of events returned.
            For performance reasons, defaults to 100.
            Uses `max` API parameter

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
            )
        if max_end:
            url += f"&maxEndTimestamp={max_end.strftime('%Y-%m-%dT00:00:00.000Z')}"
        if min_end:
            url += f"&minEndTimestamp={min_end.strftime('%Y-%m-%dT00:00:00.000Z')}"
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
            if event['id'] == uid:
                return event
