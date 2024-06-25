#!/usr/bin/env python

import argparse
import asyncio

import ics

from config import password, username
from spond import spond

DESCRIPTION = """
Read in iCal events from .ics file[s] and post them to Spond.
""".strip()


def ics2spond(event):
    """Create Spond event dictionary from ics.Event"""

    return {
        "heading": event.name,
        "description": event.description,
        "startTimestamp": event.begin.isoformat(),
        "endTimestamp": event.end.isoformat(),
        "location": {"feature": event.location},
    }


async def post_events(args, gid=None, owners=[]):
    """
    Read Calendar from .ics file[s] and post all events to Spond.

    Parameters
    ----------
    args : argparse.Namespace
        Command line arguments and options returned by ArgumentParser.parse_args(),
        containing options and file name[s] (wildcards supported).
    gid : str
        'id' of Spond group to post to (default: first group from `get_groups()` for user).
    owners : list
        list of user's {'id': uid} (default: [user] from `config.username`).
    """

    s = spond.Spond(username=username, password=password)

    if len(owners) == 0:
        user = await s.get_person(username)
        owners = [user["profile"]]

    if gid is None:
        groups = await s.get_groups()
        for mygroup in groups:
            if mygroup["contactPerson"]["id"] == owners[0]["id"]:
                break
        else:
            raise ValueError(f"No group with contact person {owners[0]['id']} found")
        recipients = {"group": mygroup}
    else:
        recipients = {"group": {"id": gid}}

    if not args.quiet:
        print(f"Posting as {username} ({owners[0]['id']}): {recipients['group']['id']}")

    for filename in args.filename:  # Support wildcards
        if not args.quiet:
            print(f"Reading {filename}:")
        calendar = ics.Calendar(open(filename).read())
        for event in calendar.events:
            updates = {"owners": owners, "recipients": recipients}
            updates.update(ics2spond(event))
            uid = getattr(event, "uid", "")
            if args.verbose:
                print(event.serialize())
            elif not args.quiet:
                print(event.name)
            events = await s.update_event(uid, updates)
    await s.clientsession.close()


def main(args=None):
    """The main function called by the `postics` script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-v",
        "--verbose",
        default=False,
        action="store_true",
        help="verbose mode; echo full iCal events parsed",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        default=False,
        action="store_true",
        help="quiet mode; do not echo iCal event names",
    )
    parser.add_argument(
        "-g", "--gid", default=None, help="specify Spond group ID of recipients group"
    )
    parser.add_argument(
        "filename",
        nargs="+",
        help="Path to one or more ics files; wildcards are supported",
    )

    args = parser.parse_args(args)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.run(post_events(args, gid=args.gid))


if __name__ == "__main__":
    main()
