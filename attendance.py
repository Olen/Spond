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
    s = spond.Spond(username=username, password=password)
    events = await s.get_events(min_start=args.f, max_start=args.t)

    if not os.path.exists("./exports"):
        os.makedirs("./exports")

    for e in events:
        base_filename = _sanitise_chars(f"{e['startTimestamp']}-{e['heading']}")
        filename = os.path.join("./exports", base_filename + ".csv")
        with open(filename, "w", newline="") as csvfile:
            spamwriter = csv.writer(
                csvfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL
            )

            spamwriter.writerow(
                ["Start", "End", "Description", "Name", "Answer", "Organizer"]
            )
            for o in e["owners"]:
                try:
                    person = await s.get_person(o["id"])
                except KeyError:
                    full_name = o["id"]
                else:
                    full_name = person["firstName"] + " " + person["lastName"]
                spamwriter.writerow(
                    [
                        e["startTimestamp"],
                        e["endTimestamp"],
                        e["heading"],
                        full_name,
                        o["response"],
                        "X",
                    ]
                )
            if args.a is True:
                for r in e["responses"]["acceptedIds"]:
                    try:
                        person = await s.get_person(r)
                    except KeyError:
                        full_name = r
                    else:
                        full_name = person["firstName"] + " " + person["lastName"]
                    spamwriter.writerow(
                        [
                            e["startTimestamp"],
                            e["endTimestamp"],
                            e["heading"],
                            full_name,
                            "accepted",
                        ]
                    )
                for r in e["responses"]["declinedIds"]:
                    try:
                        person = await s.get_person(r)
                    except KeyError:
                        full_name = r
                    else:
                        full_name = person["firstName"] + " " + person["lastName"]
                    spamwriter.writerow(
                        [
                            e["startTimestamp"],
                            e["endTimestamp"],
                            e["heading"],
                            full_name,
                            "declined",
                        ]
                    )
                for r in e["responses"]["unansweredIds"]:
                    try:
                        person = await s.get_person(r)
                    except KeyError:
                        full_name = r
                    else:
                        full_name = person["firstName"] + " " + person["lastName"]
                    spamwriter.writerow(
                        [
                            e["startTimestamp"],
                            e["endTimestamp"],
                            e["heading"],
                            full_name,
                            "unanswered",
                        ]
                    )
                for r in e["responses"]["unconfirmedIds"]:
                    try:
                        person = await s.get_person(r)
                    except KeyError:
                        full_name = r
                    else:
                        full_name = person["firstName"] + " " + person["lastName"]
                    spamwriter.writerow(
                        [
                            e["startTimestamp"],
                            e["endTimestamp"],
                            e["heading"],
                            full_name,
                            "unconfirmed",
                        ]
                    )
                for r in e["responses"]["waitinglistIds"]:
                    try:
                        person = await s.get_person(r)
                    except KeyError:
                        full_name = r
                    else:
                        full_name = person["firstName"] + " " + person["lastName"]
                    spamwriter.writerow(
                        [
                            e["startTimestamp"],
                            e["endTimestamp"],
                            e["heading"],
                            full_name,
                            "waitinglist",
                        ]
                    )

    await s.clientsession.close()


def _sanitise_chars(input_str: str) -> str:
    output_str = str(input_str).strip().replace(" ", "_")
    return re.sub(r"(?u)[^-\w.]", "", output_str)


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())
