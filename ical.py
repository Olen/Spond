#!/usr/bin/env python3

import asyncio
import os

from ics import Calendar, Event

from config import password, username
from spond import spond

if not os.path.exists("./exports"):
    os.makedirs("./exports")

ics_file = os.path.join("./exports", "spond.ics")


async def main():
    s = spond.Spond(username=username, password=password)
    c = Calendar()
    c.method = "PUBLISH"
    events = await s.get_events()
    for event in events:
        e = Event()
        e.uid = event["id"]
        e.name = event["heading"]
        e.description = event["description"]
        e.begin = event["startTimestamp"]
        e.end = event["endTimestamp"]
        e.sequence = event["updated"]
        if "cancelled" in event and event["cancelled"]:
            e.status = "Cancelled"
        if "location" in event:
            e.location = "{}, {}".format(
                event["location"].get("feature"), event["location"].get("address")
            )
        c.events.add(e)
    with open(ics_file, "w") as out_file:
        out_file.writelines(c)
    await s.clientsession.close()


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())
