# Spond
![spond logo](https://github.com/Olen/Spond/blob/main/images/spond-logo.png?raw=true)

Simple library with some example scripts to access data from Spond.

## Install

`pip install spond`

## Usage

You need a username and password from Spond



### Example code

```
import asyncio
from spond import spond

username = 'my@mail.invalid'
password = 'Pa55worD'

async def main():
    s = spond.Spond(username=username, password=password)
    groups = await s.getGroups()
    for group in groups:
        print(group['name'])
    await s.clientsession.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())

```

## Functions

### getGroups()
Gets all your group memberships and all members of those groups

### getEvents([end_time])
Gets up to 100 events.

Optional `end_time` parameter determines the earliest date from which events are returned.
Pass a `datetime` to get earlier events, e.g.:
```
events = await spond_session.getEvents(datetime.now() - timedelta(days=365))
```
If omitted, returns events from today - 14 days.


### getEventsBetween(start_time, end_time)
Gets up to 100 events.

Required `start_time` and `end_time` parameters determines the earliest and latest date from which events are returned.
Both expect a `datetime` object, e.g.:
```
start_time = datetime.now() - timedelta(days=30)
end_time = datetime.now() + timedelta(days=30)

events = await spond_session.getEventsBetween(start_time, end_time)
```
Will return _up to_ 100 events starting from 30 days in the past until 30 days in the future.



### getPerson()
Get information about a member

### getMessages()
Get all your messages

### sendMessage(recipient, text)
Send a message to `recipient` with the content `text`

