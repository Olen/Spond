"""Dump each group's full JSON representation to a per-group file.

Uses the v2.x typed-object surface. `group.model_dump_json(by_alias=True)`
serialises a typed `Group` instance back to JSON in Spond's wire shape —
the equivalent of the raw dict the pre-OO API returned.
"""

import asyncio
from pathlib import Path

from config import password, username

from spond import spond

EXPORT_DIRPATH = Path("./exports")


async def main() -> None:
    async with spond.Spond(username=username, password=password) as s:
        groups = await s.get_groups() or []

    EXPORT_DIRPATH.mkdir(exist_ok=True)
    keepcharacters = (" ", ".", "_")

    for group in groups:
        base_filename = "".join(
            c for c in group.name if c.isalnum() or c in keepcharacters
        ).rstrip()
        json_filepath = EXPORT_DIRPATH / f"{base_filename}.json"
        print(json_filepath)
        json_filepath.write_text(group.model_dump_json(by_alias=True, indent=4))


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())
