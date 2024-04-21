"""Use Spond 'get' functions to summarise available data.

Intended as a simple end-to-end test for assurance when making changes.
Uses all existing group, event, message `get_` methods.
Doesn't yet use `get_person(id)` or any `send_`, `update_` methods."""

import asyncio
import random

from config import password, username
from spond import spond

DUMMY_ID = "DUMMY_ID"


async def main() -> None:
    s = spond.Spond(username=username, password=password)

    print("Getting all groups...")
    groups = await s.get_groups()
    print(f"{len(groups)} groups:")
    for i, group in enumerate(groups):
        print(f"[{i}] {_group_summary(group)}")

    print("Getting a random group by id...")
    random_group_id = random.choice(groups)["id"]
    group = await s.get_group(random_group_id)
    print(f"{_group_summary(group)}")

    print("\nGetting a nonexistent group by id to check exception handling...")
    try:
        await s.get_group(DUMMY_ID)
    except IndexError as error:
        print(f"Exception raised: {error!r}")

    # EVENTS

    print("\nGetting up to 10 events...")
    events = await s.get_events(max_events=10)
    print(f"{len(events)} events:")
    for i, event in enumerate(events):
        print(f"[{i}] {_event_summary(event)}")

    print("Getting a random event by id...")
    random_event_id = random.choice(events)["id"]
    event = await s.get_event(random_event_id)
    print(f"{_event_summary(event)}")

    print("\nGetting a nonexistent event by id to check exception handling...")
    try:
        await s.get_event(DUMMY_ID)
    except IndexError as error:
        print(f"Exception raised: {error!r}")

    # MESSAGES

    print("\nGetting up to 10 messages...")
    messages = await s.get_messages()
    print(f"{len(messages)} messages:")
    for i, message in enumerate(messages):
        print(f"[{i}] {_message_summary(message)}")

    # No `get_message(id)` function

    await s.clientsession.close()


def _group_summary(group) -> str:
    return f"id: {group['id']}, " f"name: {group['name']}"


def _event_summary(event) -> str:
    return (
        f"id: {event['id']}, "
        f"name: {event['heading']}, "
        f"startTimestamp: {event['startTimestamp']}"
    )


def _message_summary(message) -> str:
    return (
        f"id: {message['id']}, "
        f"timestamp: {message['message']['timestamp']}, "
        f"text: {_abbreviate(message['message']['text'] if message['message'].get('text') else '', length=64)}, "
    )


def _abbreviate(text, length) -> str:
    """Abbreviate long text, normalising line endings to escape characters."""
    escaped_text = repr(text)
    if len(text) > length:
        return f"{escaped_text[0:length]}[…]"
    return f"{escaped_text}"


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())
