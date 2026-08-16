"""Typed `Comment` model — replaces the raw `list[dict]` previously
exposed by `Post.comments` and `Event.comments`.

Comments are nested children of Posts and Events. They're typed for
attribute access and forward-compat (`extra="allow"`), but carry no
ActiveRecord operations of their own — the write surface lives on
the parent (`post.add_comment(text)`). Spond doesn't expose
comment-edit or comment-delete endpoints in the consumer API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

from ._compat import DictCompatModel


class Comment(DictCompatModel):
    """A single comment attached to a `Post` or `Event`.

    Spond emits comments with this stable shape:

    ```json
    {
        "id": "<uid>",
        "fromProfileId": "<author profile uid>",
        "timestamp": "<ISO datetime>",
        "text": "<comment body>",
        "reactions": {}
    }
    ```

    All fields except `uid` are optional in the SDK so a future API
    drift (e.g. system-generated comments without a `fromProfileId`)
    doesn't crash the whole `get_posts()` payload.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    uid: str = Field(alias="id")
    from_profile_uid: str | None = Field(default=None, alias="fromProfileId")
    """Profile UID of the comment author. Absent on system-generated
    comments (if Spond ever emits any)."""
    timestamp: datetime | None = None
    text: str = ""
    reactions: dict[str, Any] = Field(default_factory=dict)
    """Emoji-reactions map keyed by reaction kind. Empty for unreacted
    comments. Unmodelled — values vary by Spond release."""

    def __str__(self) -> str:
        ts = self.timestamp.isoformat() if self.timestamp else "?"
        snippet = self.text[:40] + ("…" if len(self.text) > 40 else "")
        return (
            f"Comment(uid={self.uid!r}, from={self.from_profile_uid!r}, "
            f"ts={ts}, text={snippet!r})"
        )

    def _natural_key(self) -> tuple | None:
        """uid when set; otherwise (from_profile_uid, timestamp, text)
        for the rare case of a freshly-constructed comment with no uid yet."""
        if self.uid:
            return ("Comment", self.uid)
        if self.from_profile_uid or self.timestamp or self.text:
            return (
                "Comment",
                None,
                self.from_profile_uid,
                self.timestamp,
                self.text,
            )
        return None
