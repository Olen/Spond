# Spond
![spond logo](https://github.com/Olen/Spond/blob/main/images/spond-logo.png?raw=true)

Simple, unofficial library with some example scripts to access data from the [Spond](https://spond.com/) API.

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

## Key methods

### get_groups()

Get details of all your group memberships and all members of those groups.

### get_events([params])
Get details of events, limited to 100 by default.

### get_person()
Get a member's details.

### get_messages()
Get all your messages.

### send_message(recipient, text)
Send a message to `recipient` with the content `text`.

## Example scripts

The following scripts are included as examples.  Some of the scripts might require additional packages to be installed (csv, ical etc).

Rename the file `config.py.sample` to `config.py` and add your username and password to the file before running the samples.

### ical.py
Generates an ics-file of upcoming events.

### groups.py
Generates a json-file for each group you are a member of.

### attendance.py &lt;-f from_date&gt; &lt;-t to_date&gt; [-a]
Generates a csv-file for each event between `from_date` and `to_date` with attendance status of all organizers.  The optional parameter `-a` also includes all members that has been invited.
