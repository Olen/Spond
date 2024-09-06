"""Use Spond 'get' functions to summarise available data.

Intended as a simple end-to-end test for assurance when making changes, where there are
gaps in test suite coverage.

Doesn't yet use `get_person(user)` or any `send_`, `update_` methods."""

import asyncio
import tempfile
from typing import TYPE_CHECKING

from config import club_id, password, username
from spond import club, spond

if TYPE_CHECKING:
    from spond import JSONDict

DUMMY_ID = "DUMMY_ID"

MAX_EVENTS = 10
MAX_CHATS = 10
MAX_TRANSACTIONS = 10


async def main() -> None:
    s = spond.Spond(username=username, password=password)

    # GROUPS

    print("\nGetting all groups...")
    groups = await s.get_groups()
    print(f"{len(groups)} groups:")
    for i, group in enumerate(groups):
        print(f"[{i}] {_group_summary(group)}")

    # EVENTS

    print(f"\nGetting up to {MAX_EVENTS} events...")
    events = await s.get_events(max_events=MAX_EVENTS)
    print(f"{len(events)} events:")
    for i, event in enumerate(events):
        print(f"[{i}] {_event_summary(event)}")

    # CHATS (MESSAGES)

    print(f"\nGetting up to {MAX_CHATS} chats...")
    chats = await s.get_messages(max_chats=MAX_CHATS)
    print(f"{len(chats)} chats:")
    for i, chat in enumerate(chats):
        print(f"[{i}] {_chat_summary(chat)}")

    # ATTENDANCE EXPORT

    print("\nGetting attendance report for the first event...")
    e = events[0]
    data = await s.get_event_attendance_xlsx(e["id"])
    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=".xlsx", delete=False
    ) as temp_file:
        temp_file.write(data)
        print(f"Check out {temp_file.name}")

    await s.clientsession.close()

    # SPOND CLUB
    sc = club.SpondClub(username=username, password=password)
    print(f"\nGetting up to {MAX_TRANSACTIONS} transactions...")
    transactions = await sc.get_transactions(
        club_id=club_id, max_items=MAX_TRANSACTIONS
    )
    print(f"{len(transactions)} transactions:")
    for i, t in enumerate(transactions):
        print(f"[{i}] {_transaction_summary(t)}")
    await sc.clientsession.close()


def _group_summary(group: JSONDict) -> str:
    return f"id='{group['id']}', " f"name='{group['name']}'"


def _event_summary(event: JSONDict) -> str:
    return (
        f"id='{event['id']}', "
        f"heading='{event['heading']}', "
        f"startTimestamp='{event['startTimestamp']}'"
    )


def _chat_summary(chat: JSONDict) -> str:
    msg_text = chat["message"].get("text", "")
    return (
        f"id='{chat['id']}', "
        f"timestamp='{chat['message']['timestamp']}', "
        f"text={_abbreviate(msg_text, length=64)}"
    )


def _transaction_summary(transaction: JSONDict) -> str:
    return (
        f"id='{transaction['id']}', "
        f"timestamp='{transaction['paidAt']}', "
        f"payment_name='{transaction['paymentName']}', "
        f"name={transaction['paidByName']}"
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
