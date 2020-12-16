

import asyncio
import aiohttp

class Spond():
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.apiurl = "https://spond.com/api/2.1/"
        self.clientsession = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
        self.cookie = None


    async def login(self):
        url = self.apiurl + "login"
        data = { 'email': self.username, 'password': self.password }
        async with self.clientsession.post(url, json=data) as r:
            print('JSON', await r.json())
            print('HEAD', r.headers)
            print('COOK', r.cookies['auth'])
            self.cookie = r.cookies['auth']
                # cookies = s.cookie_jar.filter_cookies('https://spond.com/api')
                # for key, cookie in cookies.items():
                #     print('Key: "%s", Value: "%s"' % (cookie.key, cookie.value))

    async def getEvents(self):
        if not self.cookie:
            await self.login()
        url = self.apiurl + "sponds/?max=100&minEndTimestamp=2020-12-15T23:00:00.000Z&order=asc&scheduled=true"
        async with self.clientsession.get(url) as r:
            print('JSON', await r.json())
            print('HEAD', r.headers)

        pass

async def main():
    spond = Spond(username="xx", password="yy")
    # await spond.login()
    await spond.getEvents()
    await spond.clientsession.close()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())

# https://spond.com/api/2.1/sponds?addProfileInfo=true&excludeRepeating=false&includeComments=false&includeHidden=false&max=100&minEndTimestamp=2020-12-15T23:00:00.000Z&order=asc&scheduled=true
