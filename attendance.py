import argparse
import asyncio
import csv
import os
import re
from datetime import date

from config import password, username
from spond import spond

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


async def main():
    session = spond.Spond(username=username, password=password)
    events = await session.get_events(min_start=args.f, max_start=args.t)

    if not os.path.exists("./exports"):
        os.makedirs("./exports")

    for e in events:
        base_filename = _sanitise_filename(f"{e['startTimestamp']}-{e['heading']}")
        filename = os.path.join("./exports", base_filename + ".csv")
        with open(filename, "w", newline="") as csvfile:
            spamwriter = csv.writer(
                csvfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL
            )

            spamwriter.writerow(
                ["Start", "End", "Description", "Name", "Answer", "Organizer"]
            )
            for o in e["owners"]:
                name = await _derive_member_name(session, o["id"])
                spamwriter.writerow(
                    [
                        e["startTimestamp"],
                        e["endTimestamp"],
                        e["heading"],
                        name,
                        o["response"],
                        "X",
                    ]
                )
            if args.a is True:
                for r in e["responses"]["acceptedIds"]:
                    name = await _derive_member_name(session, r)
                    spamwriter.writerow(
                        [
                            e["startTimestamp"],
                            e["endTimestamp"],
                            e["heading"],
                            name,
                            "accepted",
                        ]
                    )
                for r in e["responses"]["declinedIds"]:
                    name = await _derive_member_name(session, r)
                    spamwriter.writerow(
                        [
                            e["startTimestamp"],
                            e["endTimestamp"],
                            e["heading"],
                            name,
                            "declined",
                        ]
                    )
                for r in e["responses"]["unansweredIds"]:
                    name = await _derive_member_name(session, r)
                    spamwriter.writerow(
                        [
                            e["startTimestamp"],
                            e["endTimestamp"],
                            e["heading"],
                            name,
                            "unanswered",
                        ]
                    )
                for r in e["responses"]["unconfirmedIds"]:
                    name = await _derive_member_name(session, r)
                    spamwriter.writerow(
                        [
                            e["startTimestamp"],
                            e["endTimestamp"],
                            e["heading"],
                            name,
                            "unconfirmed",
                        ]
                    )
                for r in e["responses"]["waitinglistIds"]:
                    name = await _derive_member_name(session, r)
                    spamwriter.writerow(
                        [
                            e["startTimestamp"],
                            e["endTimestamp"],
                            e["heading"],
                            name,
                            "waitinglist",
                        ]
                    )

    await session.clientsession.close()


async def _derive_member_name(spond_session, member_id: str) -> str:
    """Return full name, or id if member can't be matched."""
    try:
        person = await spond_session.get_person(member_id)
    except KeyError:
        return member_id
    return f"{person['firstName']} {person['lastName']}"


def _sanitise_filename(input_str: str) -> str:
    """Strip leading/trailing whitespace, spaces to underscores, remove chars not
    alphanumeric/underscore/hyphen."""
    output_str = str(input_str).strip().replace(" ", "_")
    return re.sub(r"(?u)[^-\w.]", "", output_str)


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())
