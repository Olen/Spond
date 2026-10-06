#!/usr/bin/env python3
"""Generate an .ics calendar file from your Spond events.

Demonstrates the v2.x typed-object surface — attribute access throughout,
and `async with Spond(...)` for automatic session cleanup.
"""

import asyncio
from pathlib import Path

from config import password, username
from ics import Calendar, Event

from spond import spond

EXPORT_DIRPATH = Path("./exports")


async def main() -> None:
    async with spond.Spond(username=username, password=password) as s:
        events = await s.get_events()

    EXPORT_DIRPATH.mkdir(exist_ok=True)
    ics_filepath = EXPORT_DIRPATH / "spond.ics"

    c = Calendar()
    c.method = "PUBLISH"

    for event in events:
        e = Event()
        e.uid = event.uid
        e.name = event.heading
        # Match events expose two start times: `start_time` is the
        # kickoff, while `meetup_time` is when participants are expected
        # to arrive (Norwegian: "oppmøtetid"). Training events only have
        # `start_time`. We prefer the meet-up time so calendar
        # subscribers see when to show up, and fall back to kickoff.
        e.begin = event.meetup_time or event.start_time
        e.end = event.end_time
        e.sequence = event.updated
        e.description = event.description
        if event.cancelled:
            e.status = "Cancelled"
        if event.location:
            e.location = (
                f"{event.location.get('feature')}, {event.location.get('address')}"
            )
        c.events.add(e)

    with ics_filepath.open("w") as out_file:
        out_file.writelines(c)


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())
