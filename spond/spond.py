#!/usr/bin/env python3

import asyncio
import aiohttp

from datetime import datetime, timedelta

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

    async def getGroups(self):
        if not self.cookie:
            await self.login()
        url = self.apiurl + "groups/"
        async with self.clientsession.get(url) as r:
            self.groups = await r.json()
            return self.groups

    async def getGroup(self, uid):
        if not self.cookie:
            await self.login()
        if not self.groups:
            await self.getGroups()
        for group in self.groups:
            if group['id'] == uid:
                return group

    async def getPerson(self, user):
        if not self.cookie:
            await self.login()
        if not self.groups:
            await self.getGroups()
        for group in self.groups:
            for member in group['members']:
                if member['id'] == user or ('email' in member and member['email']) == user or member['firstName'] + " " + member['lastName'] == user or ( 'profile' in member and member['profile']['id'] == user):
                    return member
                if 'guardians' in member:
                    for guardian in member['guardians']:
                        if guardian['id'] == user or ('email' in guardian and guardian['email']) == user or guardian['firstName'] + " " + guardian['lastName'] == user or ( 'profile' in guardian and guardian['profile']['id'] == user):
                            return guardian

    async def getMessages(self):
        if not self.cookie:
            await self.login()
        url = self.chaturl + "/chats/?max=10"
        headers = { 'auth': self.auth }
        async with self.clientsession.get(url, headers=headers) as r:
            return await r.json()


    async def sendMessage(self, recipient, text):
        if not self.cookie:
            await self.login()
        url = self.chaturl + "/messages"
        data = { 'recipient': recipient, 'text': text, 'type': "TEXT" }
        headers = { 'auth': self.auth }
        r = await self.clientsession.post(url, json=data, headers=headers)
        print(r)
        return await r.json()

    async def getEvents(self, end_time = None):
        if not self.cookie:
            await self.login()
        if not end_time:
            end_time = datetime.now() - timedelta(days=14)
        url = self.apiurl + "sponds/?max=100&minEndTimestamp={}&order=asc&scheduled=true".format(end_time.strftime("%Y-%m-%dT00:00:00.000Z"))
        async with self.clientsession.get(url) as r:
            self.events = await r.json()
            return self.events

    async def getEvent(self, uid):
        if not self.cookie:
            await self.login()
        if not self.events:
            await self.getEvents()
        for event in self.events:
            if event['id'] == uid:
                return event
