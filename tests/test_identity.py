"""Tests for entity-identity equality (`__eq__` / `__hash__`) on typed models.

The `_natural_key()` hook on `DictCompatModel` drives equality and hashing.
Two typed instances compare equal when their natural keys match; the
natural key uses `uid` when set, and falls back to user-visible fields
(heading + start_time for Event, name for Group, etc.) for instances
that haven't been saved to Spond yet.

Match/Event share an entity kind so `Match("X") == Event("X")` evaluates
True — they refer to the same Spond record. Member/Guardian share the
`"Person"` kind for the same reason.
"""

from __future__ import annotations

from datetime import UTC, datetime

from spond.chat import Chat, Message
from spond.club import Transaction
from spond.event import Event
from spond.group import Group
from spond.match import Match
from spond.person import Guardian, Member
from spond.post import Post
from spond.profile import Profile
from spond.role import Role
from spond.subgroup import Subgroup

from .conftest import _MIN_EVENT_PAYLOAD


class TestUIDBasedEquality:
    """When uid is set, instances of the same entity-kind compare equal
    iff their uids match — regardless of other field values."""

    def test_two_events_with_same_uid_are_equal(self) -> None:
        a = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "EV1"})
        # Different heading, same uid → still equal
        b = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "EV1", "heading": "X"})
        assert a == b

    def test_two_events_with_different_uid_are_unequal(self) -> None:
        a = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "EV1"})
        b = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "EV2"})
        assert a != b

    def test_event_hash_matches_uid_identity(self) -> None:
        a = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "EV1"})
        b = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "EV1", "heading": "X"})
        assert hash(a) == hash(b)
        assert {a, b} == {a}  # set dedups on hash + eq

    def test_match_and_event_with_same_uid_are_equal(self) -> None:
        """Match is a subclass of Event; they share the `"Event"` entity
        kind so the same Spond record returned as `Event` or `Match`
        compares equal."""
        e = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "EV1"})
        m = Match.model_validate(
            {**_MIN_EVENT_PAYLOAD, "id": "EV1", "matchEvent": True}
        )
        assert e == m
        assert hash(e) == hash(m)

    def test_member_and_guardian_with_same_uid_are_equal(self) -> None:
        """Both inherit from Person → share the `"Person"` entity kind.
        In practice the same Spond uid never appears in both roles, but
        the equality semantics are consistent if it did."""
        mem = Member.model_validate({"id": "P1", "firstName": "A"})
        grd = Guardian.model_validate({"id": "P1", "firstName": "A"})
        assert mem == grd

    def test_group_uid_equality(self) -> None:
        a = Group.model_validate({"id": "G1", "name": "Alpha"})
        b = Group.model_validate({"id": "G1", "name": "Beta"})
        assert a == b

    def test_post_uid_equality(self) -> None:
        a = Post.model_validate({"id": "P1", "title": "Hi"})
        b = Post.model_validate({"id": "P1", "title": "Different"})
        assert a == b

    def test_chat_uid_equality(self) -> None:
        a = Chat.model_validate({"id": "C1", "name": "x"})
        b = Chat.model_validate({"id": "C1", "name": "y"})
        assert a == b

    def test_transaction_uid_equality(self) -> None:
        a = Transaction.model_validate({"id": "T1", "paymentName": "Fee"})
        b = Transaction.model_validate({"id": "T1", "paymentName": "Other"})
        assert a == b

    def test_subgroup_uid_equality(self) -> None:
        assert Subgroup.model_validate(
            {"id": "S1", "name": "x"}
        ) == Subgroup.model_validate({"id": "S1", "name": "y"})

    def test_role_uid_equality(self) -> None:
        assert Role.model_validate({"id": "R1", "name": "x"}) == Role.model_validate(
            {"id": "R1", "name": "y"}
        )


class TestNaturalKeyFallback:
    """When uid is absent (a freshly-constructed unsaved instance), the
    natural-key fallback distinguishes by user-visible fields."""

    def test_two_unsaved_events_with_same_heading_and_start_are_equal(self) -> None:
        start = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
        # Construct via model_validate without `id` — Event requires it
        # but model_construct skips validation. Use the canonical form:
        # set id="" so the natural_key falls through to the heading path.
        a = Event(uid="", heading="Demo", start_time=start, end_time=start)
        b = Event(uid="", heading="Demo", start_time=start, end_time=start)
        assert a == b
        assert hash(a) == hash(b)

    def test_two_unsaved_events_with_different_heading_are_unequal(self) -> None:
        start = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
        a = Event(uid="", heading="A", start_time=start, end_time=start)
        b = Event(uid="", heading="B", start_time=start, end_time=start)
        assert a != b

    def test_unsaved_event_unequal_to_saved_with_same_fields(self) -> None:
        """A saved event (with uid) and an unsaved event (without uid)
        but matching heading+start_time are NOT equal — the natural key
        includes a sentinel `None` slot for unsaved entities."""
        start = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
        saved = Event(uid="EV1", heading="Demo", start_time=start, end_time=start)
        unsaved = Event(uid="", heading="Demo", start_time=start, end_time=start)
        assert saved != unsaved

    def test_unsaved_group_by_name(self) -> None:
        a = Group(uid="", name="Cool Group")
        b = Group(uid="", name="Cool Group")
        assert a == b
        assert a != Group(uid="", name="Other")

    def test_unsaved_person_by_name_and_email(self) -> None:
        a = Member(uid="", first_name="Alice", last_name="Smith", email="a@b.invalid")
        b = Member(uid="", first_name="Alice", last_name="Smith", email="a@b.invalid")
        assert a == b
        # Differ on email — not equal
        c = Member(
            uid="", first_name="Alice", last_name="Smith", email="other@b.invalid"
        )
        assert a != c

    def test_unsaved_profile_by_name(self) -> None:
        a = Profile(uid="", first_name="Ola", last_name="N")
        b = Profile(uid="", first_name="Ola", last_name="N")
        assert a == b

    def test_unsaved_post_by_title_and_timestamp(self) -> None:
        ts = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
        a = Post(uid="", title="Hi", timestamp=ts)
        b = Post(uid="", title="Hi", timestamp=ts)
        assert a == b


class TestMessageNaturalKey:
    """Message has no uid — identity is `(chat_id, msg_num)`."""

    def test_messages_with_same_chat_id_and_num_are_equal(self) -> None:
        a = Message.model_validate({"chatId": "C1", "msgNum": 7, "text": "hi"})
        b = Message.model_validate({"chatId": "C1", "msgNum": 7, "text": "different"})
        assert a == b
        assert hash(a) == hash(b)

    def test_messages_with_different_msg_num_are_unequal(self) -> None:
        a = Message.model_validate({"chatId": "C1", "msgNum": 7})
        b = Message.model_validate({"chatId": "C1", "msgNum": 8})
        assert a != b


class TestUseAsCollectionKey:
    """The motivating use case for natural-key equality: typed models as
    set members and dict keys."""

    def test_event_dedup_in_set(self) -> None:
        a = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "EV1"})
        b = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "EV1", "heading": "X"})
        c = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "EV2"})
        assert len({a, b, c}) == 2

    def test_member_as_dict_key(self) -> None:
        m1 = Member.model_validate({"id": "P1", "firstName": "A", "lastName": "B"})
        m2 = Member.model_validate({"id": "P1", "firstName": "A", "lastName": "B"})
        d = {m1: "first"}
        # Same uid → same key, overwrites
        d[m2] = "second"
        assert len(d) == 1
        assert d[m1] == "second"


class TestCrossTypeEquality:
    """An entity of one kind should never equal an entity of a different
    kind — even if their uids happen to collide."""

    def test_event_unequal_to_group_with_same_uid(self) -> None:
        e = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "X"})
        g = Group.model_validate({"id": "X"})
        assert e != g

    def test_event_unequal_to_non_typed_object(self) -> None:
        e = Event.model_validate({**_MIN_EVENT_PAYLOAD, "id": "X"})
        assert e != "X"
        assert e != {"id": "X"}
        assert e != 42
