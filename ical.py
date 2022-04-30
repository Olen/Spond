import asyncio
from spond import spond
from ics import Calendar, Event
from config import username, password

ics_file = 'spond.ics'


async def main():
    s = spond.Spond(username=username, password=password)
    c = Calendar()
    c.method = 'PUBLISH'
    events = await s.getEvents()
    for event in events:
        e = Event()
        e.uid = event['id']
        e.name = event['heading']
        e.description = event['description']
        e.begin = event['startTimestamp']
        e.end = event['endTimestamp']
        e.sequence = event['updated']
        if 'cancelled' in event and event['cancelled']:
            e.status = 'Cancelled'
        if 'location' in event:
            e.location = "{}, {}".format(event['location']['feature'], event['location']['address'])
        c.events.add(e)
    with open(ics_file, 'w') as out_file:
        out_file.writelines(c)
    await s.clientsession.close()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())

