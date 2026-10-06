"""Per-event attendance CSVs for organisers.

Uses the v2.x typed-object surface throughout — attribute access,
typed `event.responses`, the `Event.response_for(uid)` convenience
property, and the `_resolve_uids_to_persons()`-based member helpers.
"""

import argparse
import asyncio
import csv
import re
from datetime import date
from pathlib import Path

from config import password, username

from spond import spond

EXPORT_DIRPATH = Path("./exports")

parser = argparse.ArgumentParser(
    description="Creates an attendance.csv for organizers of events."
)
parser.add_argument(
    "-f",
    "--from",
    help="First date to query for. Date is included in results (format YYYY-MM-DD)",
    type=date.fromisoformat,
    dest="f",
)
parser.add_argument(
    "-t",
    "--to",
    help="Last date to query for. Date is excluded from results (format YYYY-MM-DD)",
    type=date.fromisoformat,
    dest="t",
)
parser.add_argument(
    "-a", help="Also include all members", default=False, action="store_true"
)
args = parser.parse_args()


async def main() -> None:
    async with spond.Spond(username=username, password=password) as session:
        events = await session.get_events(min_start=args.f, max_start=args.t)
        EXPORT_DIRPATH.mkdir(exist_ok=True)

        for e in events:
            base_filename = _sanitise_filename(f"{e.start_time}-{e.heading}")
            filepath = EXPORT_DIRPATH / f"{base_filename}.csv"
            with filepath.open("w", newline="") as csvfile:
                writer = csv.writer(
                    csvfile,
                    delimiter=",",
                    quotechar='"',
                    quoting=csv.QUOTE_MINIMAL,
                )
                writer.writerow(
                    ["Start", "End", "Description", "Name", "Answer", "Organizer"]
                )

                # Organisers first (event.owners is list[dict] —
                # individual owner shape isn't a typed model in v2.x).
                for o in e.owners:
                    name = await _derive_member_name(session, o.get("id", ""))
                    writer.writerow(
                        [
                            e.start_time,
                            e.end_time,
                            e.heading,
                            name,
                            o.get("response", ""),
                            "X",
                        ]
                    )

                if args.a:
                    # Each response bucket gets its own pass — using the
                    # typed `event.responses` instead of dict subscripts.
                    buckets = (
                        ("accepted", e.responses.accepted_uids),
                        ("declined", e.responses.declined_uids),
                        ("unanswered", e.responses.unanswered_uids),
                        ("unconfirmed", e.responses.unconfirmed_uids),
                        ("waitinglist", e.responses.waiting_list_uids),
                    )
                    for status, uids in buckets:
                        for uid in uids:
                            name = await _derive_member_name(session, uid)
                            writer.writerow(
                                [e.start_time, e.end_time, e.heading, name, status]
                            )


async def _derive_member_name(spond_session, member_id: str) -> str:
    """Return full name, or id if member can't be matched."""
    try:
        person = await spond_session.get_person(member_id)
    except KeyError:
        return member_id
    return person.full_name


def _sanitise_filename(input_str: str) -> str:
    """Strip leading/trailing whitespace, spaces to underscores, remove chars not
    alphanumeric/underscore/hyphen."""
    output_str = str(input_str).strip().replace(" ", "_")
    return re.sub(r"(?u)[^-\w.]", "", output_str)


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())
