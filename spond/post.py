"""Typed `Post` model — group-wall announcements and their comments.

`Post`s are the announcement-style messages posted to a Group's wall (as
opposed to chat messages or events). Returned by `Spond.get_posts()`.

Comments on posts are not yet modelled as a separate class — they're
exposed as a `list[dict]`. Modelling them is a follow-up (the comment
shape is small but varies by Spond version).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

from ._compat import DictCompatModel


class Post(DictCompatModel):
    """A post on a Group's wall (announcement, not a chat message)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    uid: str = Field(alias="id")
    type: str = "PLAIN"
    title: str | None = None
    body: str | None = None
    timestamp: datetime
    group_uid: str | None = Field(default=None, alias="groupId")
    subgroup_uids: list[str] = Field(default_factory=list, alias="subGroupIds")
    owner_uid: str | None = Field(default=None, alias="ownerId")
    visibility: str | None = None
    """e.g. \"ADULTS_GUARDIANS_ONLY\", \"ALL\"."""
    unread: bool = False
    muted: bool = False
    comments_disabled: bool = Field(default=False, alias="commentsDisabled")
    select_member_poll: bool = Field(default=False, alias="selectMemberPoll")
    media: list[Any] = Field(default_factory=list)
    attachments: list[Any] = Field(default_factory=list)
    comments: list[dict[str, Any]] = Field(default_factory=list)
    """Comment dicts. Only populated when fetched with
    `include_comments=True` (the default for `Spond.get_posts()`). Currently
    typed as raw `dict` — a `Comment` class is a possible future refinement."""

    def __str__(self) -> str:
        return (
            f"Post(uid={self.uid!r}, title={self.title!r}, "
            f"timestamp={self.timestamp.isoformat()})"
        )
