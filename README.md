# Spond
![spond logo](https://github.com/Olen/Spond/blob/main/images/spond-logo.png?raw=true)

Simple library with some example scripts to access data from Spond.


## Usage

Rename `config.py.sample` to config.py and set your Spond username and password in that file.

### Example code

```
import asyncio
from spond import spond
from config import username, password
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

### getEvents()
Gets all upcoming events

### getPerson()
Get information about a member

### getMessages()
Get all your messages

### sendMessage(receipient, text)
Send a message to `receipient` with the content `text`

