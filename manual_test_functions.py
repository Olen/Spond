"""Use Spond 'get' functions to summarise available data.

Intended as a simple end-to-end test for assurance when making changes, where there are s
gaps in test suite coverage.

Doesn't yet use `get_person(user)` or any `send_`, `update_` methods."""

import asyncio

from config import password, username
from spond import spond

DUMMY_ID = "DUMMY_ID"


async def main() -> None:
    s = spond.Spond(username=username, password=password)

    # GROUPS

    print("\nGetting all groups...")
    groups = await s.get_groups()
    print(f"{len(groups)} groups:")
    for i, group in enumerate(groups):
        print(f"[{i}] {_group_summary(group)}")

    # EVENTS

    print("\nGetting up to 10 events...")
    events = await s.get_events(max_events=10)
    print(f"{len(events)} events:")
    for i, event in enumerate(events):
        print(f"[{i}] {_event_summary(event)}")

    # MESSAGES

    print("\nGetting up to 10 messages...")
    messages = await s.get_messages()
    print(f"{len(messages)} messages:")
    for i, message in enumerate(messages):
        print(f"[{i}] {_message_summary(message)}")

    await s.clientsession.close()


def _group_summary(group) -> str:
    return f"id='{group['id']}', " f"name='{group['name']}'"


def _event_summary(event) -> str:
    return (
        f"id='{event['id']}', "
        f"heading='{event['heading']}', "
        f"startTimestamp='{event['startTimestamp']}'"
    )


def _message_summary(message) -> str:
    return (
        f"id='{message['id']}', "
        f"timestamp='{message['message']['timestamp']}', "
        f"text={_abbreviate(message['message']['text'] if message['message'].get('text') else '', length=64)}, "
    )


def _abbreviate(text, length) -> str:
    """Abbreviate long text, normalising line endings to escape characters."""
    escaped_text = repr(text)
    if len(text) > length:
        return f"{escaped_text[:length]}[…]"
    return escaped_text


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())
