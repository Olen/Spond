import asyncio
import json
from pathlib import Path

from config import password, username

from spond import spond

EXPORT_DIRPATH = Path("./exports")


async def main() -> None:
    s = spond.Spond(username=username, password=password)
    groups = await s.get_groups()
    EXPORT_DIRPATH.mkdir(exist_ok=True)

    for group in groups:
        name = group["name"]
        data = json.dumps(group, indent=4, sort_keys=True)
        keepcharacters = (" ", ".", "_")
        base_filename = "".join(
            c for c in name if c.isalnum() or c in keepcharacters
        ).rstrip()
        json_filepath = EXPORT_DIRPATH / f"{base_filename}.json"
        print(json_filepath)
        with json_filepath.open("w") as out_file:
            out_file.write(data)

    await s.clientsession.close()


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())
