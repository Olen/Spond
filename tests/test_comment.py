"""Tests for the typed `Comment` model.

Covers field mapping (alias resolution), natural-key equality with
Post/Event coverage of typed comments, and the resilience defaults
(only `uid` is strictly required)."""

from __future__ import annotations

from datetime import datetime

from spond.comment import Comment
from spond.event import Event
from spond.post import Post

from .conftest import _MIN_EVENT_PAYLOAD

_RAW_COMMENT = {
    "id": "CMT1",
    "fromProfileId": "PROF1",
    "timestamp": "2026-05-15T10:00:00Z",
    "text": "Looks great!",
    "reactions": {},
}


class TestCommentParsing:
    def test_parses_all_fields(self) -> None:
        c = Comment.model_validate(_RAW_COMMENT)
        assert c.uid == "CMT1"
        assert c.from_profile_uid == "PROF1"
        assert c.text == "Looks great!"
        assert c.reactions == {}
        assert c.timestamp is not None
        assert c.timestamp.year == 2026

    def test_minimal_only_uid_required(self) -> None:
        """All non-uid fields have defaults; only `id` is strictly required.
        Locks in the resilience guarantee against API drift."""
        c = Comment.model_validate({"id": "CMT_MIN"})
        assert c.uid == "CMT_MIN"
        assert c.from_profile_uid is None
        assert c.text == ""
        assert c.timestamp is None
        assert c.reactions == {}

    def test_str_includes_uid_and_snippet(self) -> None:
        c = Comment.model_validate(_RAW_COMMENT)
        s = str(c)
        assert "CMT1" in s
        assert "Looks great!" in s

    def test_str_handles_missing_timestamp(self) -> None:
        """`__str__` must not crash when timestamp is None (same defensive
        guard as `Post.__str__` / `Event.__str__`)."""
        c = Comment.model_validate({"id": "X", "text": "no ts"})
        assert "?" in str(c)
        assert "no ts" in str(c)

    def test_long_text_is_truncated_in_str(self) -> None:
        c = Comment.model_validate({"id": "X", "text": "x" * 200})
        s = str(c)
        assert "…" in s
        assert len(s) < 200

    def test_extra_fields_preserved(self) -> None:
        """`extra="allow"` lets Spond add fields without crashing
        validation. The extras are reachable via the dict-compat shim."""
        c = Comment.model_validate({**_RAW_COMMENT, "futureField": 42})
        assert "futureField" in c
        assert c.__pydantic_extra__["futureField"] == 42


class TestCommentNaturalKey:
    """Comment uses uid when set, else (from_profile_uid, timestamp, text)."""

    def test_same_uid_equal_regardless_of_state(self) -> None:
        a = Comment.model_validate({"id": "CMT1", "text": "hi"})
        b = Comment.model_validate({"id": "CMT1", "text": "different"})
        assert a == b
        assert hash(a) == hash(b)

    def test_unsaved_equal_by_natural_key(self) -> None:
        ts = datetime.fromisoformat("2026-05-15T10:00:00+00:00")
        a = Comment(uid="", from_profile_uid="P1", timestamp=ts, text="hi")
        b = Comment(uid="", from_profile_uid="P1", timestamp=ts, text="hi")
        assert a == b


class TestCommentsOnPost:
    """`Post.comments` must materialize as typed `Comment` instances."""

    def test_post_comments_are_typed(self) -> None:
        raw = {
            "id": "POST1",
            "type": "PLAIN",
            "comments": [_RAW_COMMENT, {"id": "CMT2", "text": "second"}],
        }
        p = Post.model_validate(raw)
        assert len(p.comments) == 2
        assert all(isinstance(c, Comment) for c in p.comments)
        assert p.comments[0].text == "Looks great!"
        assert p.comments[1].uid == "CMT2"

    def test_post_with_no_comments_defaults_to_empty_list(self) -> None:
        p = Post.model_validate({"id": "P1"})
        assert p.comments == []


class TestCommentsOnEvent:
    """`Event.comments` must materialize as typed `Comment` instances too —
    same shape across the two parent kinds."""

    def test_event_comments_are_typed(self) -> None:
        raw = {**_MIN_EVENT_PAYLOAD, "comments": [_RAW_COMMENT]}
        e = Event.model_validate(raw)
        assert len(e.comments) == 1
        assert isinstance(e.comments[0], Comment)
        assert e.comments[0].text == "Looks great!"

    def test_event_with_no_comments_defaults_to_empty_list(self) -> None:
        e = Event.model_validate(_MIN_EVENT_PAYLOAD)
        assert e.comments == []
