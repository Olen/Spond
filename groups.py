import asyncio
import json
import os
from spond import spond
from config import username, password


if not os.path.exists('./exports'):
    os.makedirs('./exports')



async def main():
    s = spond.Spond(username=username, password=password)
    groups = await s.getGroups()
    for group in groups:
        name = group['name']
        data = (json.dumps(group, indent=4, sort_keys=True))
        keepcharacters = (' ','.','_')
        filename = os.path.join("./exports", "".join(c for c in name if c.isalnum() or c in keepcharacters).rstrip() + ".json")
        print(filename)
        with open(filename, 'w') as out_file:
            out_file.write(data)
        
    await s.clientsession.close()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())

