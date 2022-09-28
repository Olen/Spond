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
    groups = await s.get_groups()
    for group in groups:
        print(group['name'])
    await s.clientsession.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())

```

## Functions

### get_groups()
Gets all your group memberships and all members of those groups

### get_events([from_date])
Gets up to 100 events.

Optional `from_date` parameter determines the earliest date from which events are returned.
Pass a `datetime` to get earlier events, e.g.:
```
events = await spond_session.get_events(datetime.now() - timedelta(days=365))
```
If omitted, returns events from today - 14 days.


### get_events_between(from_date, to_date)
Gets up to 100 events.

Required `from_date` and `to_date` parameters determines the earliest and latest date from which events are returned.
Both expect a `datetime` object, e.g.:
```
from_date = datetime.now() - timedelta(days=30)
to_date = datetime.now() + timedelta(days=30)

events = await spond_session.get_events_between(from_date, to_date)
```
Will return _up to_ 100 events starting from 30 days in the past until 30 days in the future.



### getPerson()
Get information about a member

### getMessages()
Get all your messages

### sendMessage(recipient, text)
Send a message to `recipient` with the content `text`

## Example scripts

The following scripts are included as examples.  Some of the scripts might require additional packages to be installed (csv, ical etc).

Rename the file `config.py.sample` to `config.py` and add your username and password to the file before running the samples.

### ical.py
Generates an ics-file of upcoming events.

### groups.py
Generates a json-file for each group you are a member of.

### attendance.py &lt;-f from_date&gt; &lt;-t to_date&gt; [-a]
Generates a csv-file for each event between `from_date` and `to_date` with attendance status of all organizers.  The optional parameter `-a` also includes all members that has been invited.
