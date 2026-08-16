"""Use Spond 'get' functions to summarise available data.

Intended as a simple end-to-end test for assurance when making changes,
where there are gaps in test suite coverage.

Uses the v2.x typed-object surface throughout. Doesn't yet exercise
`get_person(user)` or any `send_` / save / delete methods — those
have dedicated test coverage in the suite.
"""

import asyncio
import tempfile

from config import club_id, password, username

from spond import club, spond
from spond.chat import Chat
from spond.club import Transaction
from spond.event import Event
from spond.group import Group
from spond.post import Post
from spond.profile import Profile

MAX_EVENTS = 10
MAX_CHATS = 10
MAX_POSTS = 10
MAX_TRANSACTIONS = 10


async def main() -> None:
    # ----------------------------------------------------------------
    # Consumer Spond API
    # ----------------------------------------------------------------
    async with spond.Spond(username=username, password=password) as s:
        # Profile
        print("\nGetting profile...")
        profile = await s.get_profile()
        print(_profile_summary(profile))

        # Groups
        print("\nGetting all groups...")
        groups = await s.get_groups() or []
        print(f"{len(groups)} groups:")
        for i, group in enumerate(groups):
            print(f"[{i}] {_group_summary(group)}")

        # Events
        print(f"\nGetting up to {MAX_EVENTS} events...")
        events = await s.get_events(max_events=MAX_EVENTS) or []
        print(f"{len(events)} events:")
        for i, event in enumerate(events):
            print(f"[{i}] {_event_summary(event)}")

        # Chats (messages)
        print(f"\nGetting up to {MAX_CHATS} chats...")
        chats = await s.get_messages(max_chats=MAX_CHATS) or []
        print(f"{len(chats)} chats:")
        for i, chat in enumerate(chats):
            print(f"[{i}] {_chat_summary(chat)}")

        # Posts
        print(f"\nGetting up to {MAX_POSTS} posts...")
        posts = await s.get_posts(max_posts=MAX_POSTS) or []
        print(f"{len(posts)} posts:")
        for i, post in enumerate(posts):
            print(f"[{i}] {_post_summary(post)}")

        # Attendance export — exercise the v2.x ActiveRecord method
        # `event.attendance_xlsx()` (the deprecated `Spond.get_event_
        # attendance_xlsx()` wrapper still works but emits a
        # DeprecationWarning).
        if events:
            print("\nGetting attendance report for the first event...")
            data = await events[0].attendance_xlsx()
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=".xlsx",
                delete=False,
            ) as temp_file:
                temp_file.write(data)
                print(f"Check out {temp_file.name}")

    # ----------------------------------------------------------------
    # Spond Club finance API
    # ----------------------------------------------------------------
    async with club.SpondClub(username=username, password=password) as sc:
        print(f"\nGetting up to {MAX_TRANSACTIONS} transactions...")
        transactions = await sc.get_transactions(
            club_id=club_id,
            max_items=MAX_TRANSACTIONS,
        )
        print(f"{len(transactions)} transactions:")
        for i, t in enumerate(transactions):
            print(f"[{i}] {_transaction_summary(t)}")


def _profile_summary(profile: Profile) -> str:
    return (
        f"uid={profile.uid!r}, "
        f"first_name={profile.first_name!r}, "
        f"last_name={profile.last_name!r}"
    )


def _group_summary(group: Group) -> str:
    return f"uid={group.uid!r}, name={group.name!r}, members={len(group.members)}"


def _event_summary(event: Event) -> str:
    return (
        f"uid={event.uid!r}, heading={event.heading!r}, start_time={event.start_time}"
    )


def _chat_summary(chat: Chat) -> str:
    msg_text = chat.message.text if chat.message and chat.message.text else ""
    msg_ts = chat.message.timestamp if chat.message else None
    return (
        f"uid={chat.uid!r}, timestamp={msg_ts}, text={_abbreviate(msg_text, length=64)}"
    )


def _post_summary(post: Post) -> str:
    return f"uid={post.uid!r}, timestamp={post.timestamp}, title={post.title!r}"


def _transaction_summary(transaction: Transaction) -> str:
    return (
        f"uid={transaction.uid!r}, "
        f"paid_at={transaction.paid_at}, "
        f"payment_name={transaction.payment_name!r}, "
        f"paid_by={transaction.paid_by_name!r}"
    )


def _abbreviate(text: str, length: int) -> str:
    """Abbreviate long text, normalising line endings to escape characters."""
    escaped_text = repr(text)
    if len(text) > length:
        return f"{escaped_text[:length]}[…]"
    return escaped_text


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.run(main())
