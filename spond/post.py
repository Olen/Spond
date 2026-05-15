"""Typed `Post` model — group-wall announcements with ActiveRecord behaviour.

`Post`s are the announcement-style messages posted to a Group's wall (as
opposed to chat messages or events). Returned by `Spond.get_posts()`.

The write surface mirrors `Event`'s shape:

- `post.save(client=spond)` — create (no uid) or update (uid present)
- `post.delete()` — DELETE `/posts/{uid}` and prune from cache
- `post.add_comment(text)` — POST `/posts/{uid}/comments`, returns the
  new `Comment` and appends it to `post.comments`
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict, Field, PrivateAttr

from ._compat import DictCompatModel
from .comment import Comment
from .exceptions import SpondAPIError

if TYPE_CHECKING:
    from .spond import Spond


# Python field names that `Post.save()` strips from the POST payload
# on both the create and update paths. Mirrors `_EVENT_READ_ONLY_FIELDS`
# in event.py — same reasoning: server-managed timestamps and identifiers,
# per-user view state, and nested sub-resources that have their own
# endpoints (`comments` → `post.add_comment(...)`; reactions are managed
# elsewhere). Sending these back risks Spond treating stale local state
# as authoritative or, on create, having client-supplied values
# silently overridden by server-managed ones.
_POST_READ_ONLY_FIELDS = frozenset(
    {
        "owner_uid",  # set by Spond from the authenticated user
        "timestamp",  # set by Spond on create; immutable
        "unread",  # per-user view state
        "muted",  # per-user view state
        "reactions",  # has its own dedicated endpoint
        "comments",  # has its own endpoint (post.add_comment)
    }
)


class Post(DictCompatModel):
    """A post on a Group's wall (announcement, not a chat message).

    Construct via `Spond.get_posts()` — which wires `_client` for you.
    For a freshly-created post, build with `Post(...)` and call
    `await post.save(client=spond)`; subsequent `save()` calls (and
    `delete()` / `add_comment()`) use the bound client automatically.

    Example
    -------
    ```python
    async with Spond(username, password) as s:
        # Read
        posts = await s.get_posts(group_id="GRP")
        for p in posts:
            print(p.title, [c.text for c in p.comments])

        # Create
        post = Post(uid="", type="PLAIN", group_uid="GRP",
                    title="Hello", body="Welcome to the group.")
        await post.save(client=s)
        assert post.uid

        # Comment
        await post.add_comment("First!")

        # Delete
        await post.delete()
    ```
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    uid: str = Field(alias="id")
    type: str = "PLAIN"
    title: str | None = None
    body: str | None = None
    timestamp: datetime | None = None
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
    reactions: dict[str, Any] = Field(default_factory=dict)
    """Emoji-reactions map. Empty for unreacted posts."""
    comments: list[Comment] = Field(default_factory=list)
    """Typed `Comment` instances. Only populated when fetched with
    `include_comments=True` (the default for `Spond.get_posts()`)."""

    # Non-serialised reference back to the Spond client for HTTP calls.
    _client: Any = PrivateAttr(default=None)

    def __str__(self) -> str:
        # `timestamp` is optional after the resilience relaxation, so guard
        # the .isoformat() call the same way `Event.__str__` guards
        # `start_time`. Avoids `AttributeError` when Spond omits the field.
        ts = self.timestamp.isoformat() if self.timestamp else "?"
        return f"Post(uid={self.uid!r}, title={self.title!r}, timestamp={ts})"

    def _natural_key(self) -> tuple | None:
        """uid when set; otherwise (title, timestamp) for unsaved posts."""
        if self.uid:
            return ("Post", self.uid)
        if self.title or self.timestamp:
            return ("Post", None, self.title, self.timestamp)
        return None

    @classmethod
    def from_api(cls, data: dict[str, Any], client: Spond | None) -> Post:
        """Construct a `Post` from raw API data and bind the client."""
        instance = cls.model_validate(data)
        instance._client = client
        return instance

    async def save(self, client: Spond | None = None) -> Post:
        """Persist this post to Spond — universal create-or-update.

        - `self.uid` empty → POST `/posts/` to create. Mutates self in
          place with the persisted state (uid populated, server-managed
          fields copied in) and appends to `client.posts`.
        - `self.uid` set → POST `/posts/{uid}` to update. Mutates self
          with the refreshed state.

        On first save of a freshly-constructed instance, pass
        `client=spond` to bind a client; subsequent saves use the
        bound client.

        Raises
        ------
        RuntimeError
            No client is bound and `client` was not supplied.
        SpondAPIError
            Spond rejected the create or update.
        """
        if client is not None:
            self._client = client
        if self._client is None:
            raise RuntimeError(
                "Post has no client bound. Pass `client=spond` to "
                "`post.save(client=...)` on first save."
            )
        await self._client._ensure_authenticated()

        # Apply `_POST_READ_ONLY_FIELDS` on BOTH paths. On update it
        # prevents round-tripping stale local state of fields with
        # dedicated endpoints. On create the same set is excluded
        # because Spond sets `owner_uid`/`timestamp` itself, ignores
        # client-supplied `unread`/`muted` (per-user state), and the
        # `comments`/`reactions` lists are populated through their own
        # endpoints — sending them at create time risks the caller
        # accidentally seeding stale data from a Post built off another
        # post's response payload.
        payload = self.model_dump(
            by_alias=True,
            mode="json",
            exclude=_POST_READ_ONLY_FIELDS,
            exclude_unset=True,
            exclude_none=True,
        )
        payload.pop("id", None)  # never echo uid in the body
        if self.uid:
            url = f"{self._client.api_url}posts/{self.uid}"
        else:
            url = f"{self._client.api_url}posts/"

        async with self._client.clientsession.post(
            url, json=payload, headers=self._client.auth_headers
        ) as r:
            if not r.ok:
                raise SpondAPIError(r.status, await r.text(), url)
            new_data = await r.json()

        refreshed = type(self).from_api(new_data, self._client)
        is_create = not self.uid

        # Apply refreshed state to self IN PLACE (ActiveRecord contract).
        # `object.__setattr__` is used deliberately to bypass any
        # `validate_assignment=True` or custom `__setattr__` a future
        # subclass might add — the values in `refreshed` have already
        # passed full Pydantic validation via `from_api`, so re-running
        # validation per-field here would be redundant work AND would
        # incorrectly re-trigger any validators that have side effects
        # (e.g. mutation timestamps). The wholesale
        # `__pydantic_fields_set__` replacement on the line below keeps
        # `exclude_unset=True` dumps consistent with what Spond emitted.
        for field_name in type(self).model_fields:
            object.__setattr__(self, field_name, getattr(refreshed, field_name))
        extras = refreshed._pydantic_extras()
        if extras and self.__pydantic_extra__ is not None:
            self.__pydantic_extra__.update(extras)
        self.__pydantic_fields_set__ = set(refreshed.__pydantic_fields_set__)

        # Cache management. On create, prepend so subsequent
        # `get_posts(...)` filter scans find it without a re-fetch.
        if is_create:
            if self._client.posts is None:
                self._client.posts = [self]
            else:
                self._client.posts.insert(0, self)

        return self

    async def delete(self) -> None:
        """Delete this post from Spond.

        Issues `DELETE /posts/{uid}` and prunes the post from the
        client's `posts` cache.

        Raises
        ------
        RuntimeError
            The post has no client bound or no `uid` (was never
            persisted).
        SpondAPIError
            Spond rejected the delete.
        """
        if self._client is None:
            raise RuntimeError("Post has no client bound; cannot delete.")
        if not self.uid:
            raise RuntimeError(
                "Cannot delete an unsaved Post (no uid). Call save() first."
            )
        await self._client._ensure_authenticated()
        url = f"{self._client.api_url}posts/{self.uid}"
        async with self._client.clientsession.delete(
            url, headers=self._client.auth_headers
        ) as r:
            if not r.ok:
                raise SpondAPIError(r.status, await r.text(), url)
        if self._client.posts is not None:
            self._client.posts = [p for p in self._client.posts if p.uid != self.uid]

    async def add_comment(self, text: str) -> Comment:
        """Post a comment on this Post.

        Issues `POST /posts/{uid}/comments` with `{"text": text}` and
        appends the resulting `Comment` to `self.comments` in place
        so the parent post stays consistent without an explicit refresh.

        Parameters
        ----------
        text : str
            Comment body.

        Returns
        -------
        Comment
            The newly-created comment (also appended to `self.comments`).

        Raises
        ------
        RuntimeError
            No client bound, or `self.uid` is empty (the post hasn't
            been saved to Spond yet — comments need a parent uid).
        SpondAPIError
            Spond rejected the comment (e.g. `commentsDisabled=True` on
            the post).
        """
        if self._client is None:
            raise RuntimeError("Post has no client bound; cannot add comment.")
        if not self.uid:
            raise RuntimeError(
                "Cannot add a comment to an unsaved Post. Call save() first."
            )
        await self._client._ensure_authenticated()
        url = f"{self._client.api_url}posts/{self.uid}/comments"
        async with self._client.clientsession.post(
            url, json={"text": text}, headers=self._client.auth_headers
        ) as r:
            if not r.ok:
                raise SpondAPIError(r.status, await r.text(), url)
            data = await r.json()
        comment = Comment.model_validate(data)
        # Keep the parent in sync — callers reading `post.comments`
        # immediately after this call should see the new comment.
        self.comments.append(comment)
        return comment
