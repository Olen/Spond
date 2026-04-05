#!/usr/bin/env python3

import asyncio
from pathlib import Path

from config import password, username
from ics import Calendar, Event

from spond import spond

EXPORT_DIRPATH = Path("./exports")


async def main() -> None:
    s = spond.Spond(username=username, password=password)
    c = Calendar()
    c.method = "PUBLISH"
    events = await s.get_events()
    EXPORT_DIRPATH.mkdir(exist_ok=True)
    ics_filepath = EXPORT_DIRPATH / "spond.ics"

    for event in events:
        e = Event()
        e.uid = event["id"]
        e.name = event["heading"]
        e.begin = event["startTimestamp"]
        e.end = event["endTimestamp"]
        e.sequence = event["updated"]
        e.description = event.get("description")
        if "cancelled" in event and event["cancelled"]:
            e.status = "Cancelled"
        if "location" in event:
            e.location = f"{event['location'].get('feature')}, {event['location'].get('address')}"
        c.events.add(e)

    with ics_filepath.open("w") as out_file:
        out_file.writelines(c)

    await s.clientsession.close()


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())
