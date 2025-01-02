# Spond
![spond logo](https://github.com/Olen/Spond/blob/main/images/spond-logo.png?raw=true)

Simple, unofficial library with some example scripts to access data from the [Spond](https://spond.com/) API.

## Branch info

This branch WILL be a breaking change.

The goal is that all functions will return well defined objects with proper error handling and checks


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
group_id = 'C9DC791FFE63D7914D6952BE10D97B46'  # fake 

async def main():
    s = spond.Spond(username=username, password=password)
    group = await s.get_group(group_id)
    print(group['name'])
    await s.clientsession.close()

asyncio.run(main())

```

## Key methods

### get_groups()

Get details of all your group memberships and all members of those groups.

### get_events([group_id, subgroup_id, include_scheduled, max_end, min_end, max_start, min_start, max_events])

Get details of events, limited to 100 by default.
Optional parameters allow filtering by start and end datetimes, group and subgroup; more events to be returned; inclusion of 'scheduled' events.

### get_person()
Get a member's details.

### get_messages(max_chats=100)
Get chats, limited to 100 by default.
Optional parameter allows more events to be returned.

### send_message(text, user=None, group_uid=None, chat_id=None)
Send a message with content `text`.
Either specify an existing `chat_id`, or both `user` and `group_uid` for a new chat.

### get_event_attendance_xlsx()
Get Excel attendance report for a single event, available via the web client.

### change_response()
Change a member's response for an event (e.g. accept/decline)

## Example scripts

The following scripts are included as examples.  Some of the scripts might require additional packages to be installed (csv, ical etc).

Rename the file `config.py.sample` to `config.py` and add your username and password to the file before running the samples.

### ical.py
Generates an ics-file of upcoming events.

### groups.py
Generates a json-file for each group you are a member of.

### attendance.py &lt;-f from_date&gt; &lt;-t to_date&gt; [-a]
Generates a csv-file for each event between `from_date` and `to_date` with attendance status of all organizers.  The optional parameter `-a` also includes all members that has been invited.

### transactions.py
Generates a csv-file for transactions / payments appeared in [Spond Club](https://www.spond.com/spond-club-overview/) > Finance > Payments.

## AsyncIO
[Asyncio](https://docs.python.org/3/library/asyncio.html) might seem intimidating in the beginning, but for basic stuff, it is quite easy to follow the examples above, and just remeber to prefix functions that use the API with `async def ...` and to `await` all API-calls and all calls to said functions.

[This article](https://realpython.com/async-io-python/) will give a nice introduction to both why, when and how to use asyncio in projects.

