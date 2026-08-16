"""Typed `Chat` and `Message` models for the in-app chat API.

Spond's chat lives on a separate host (`self._chat_url`) with a separate
auth token (`self._auth`), set up lazily by `Spond._login_chat`. Each
chat thread carries a single embedded `message` representing the most
recent post in the thread; full message history isn't exposed by the
core API surface.

The `message.type` field discriminates between several payload shapes:

| message.type      | Sender             | Extra payload field        |
|-------------------|--------------------|----------------------------|
| `TEXT`            | regular user       | `text`                     |
| `IMAGES`          | regular user       | `images: list`             |
| `RENAME`          | regular user       | `new_name`                 |
| `SPOND`           | regular user       | `spond` (event share)      |
| `INTERNAL_PROMO`  | none (system)      | `internal_promo`           |
| `CAMPAIGN`        | none (system)      | `campaign`                 |

Common fields (`chat_id`, `msg_num`, `timestamp`, `type`, `reactions`)
are modelled directly; the type-specific extras are declared as
optional fields. Anything Spond adds later passes through `extra="allow"`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict, Field, PrivateAttr

from ._compat import DictCompatModel

if TYPE_CHECKING:
    from .spond import Spond


class Message(DictCompatModel):
    """A single chat message — almost always the most recent in a `Chat`.

    Only the common header fields (`chat_id`, `msg_num`, `timestamp`,
    `type`, `reactions`) are guaranteed across all message variants.
    Type-specific extras (`text`, `images`, `new_name`, etc.) are
    optional; consumers should branch on `type` before reading them.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    chat_id: str | None = Field(default=None, alias="chatId")
    msg_num: int | None = Field(default=None, alias="msgNum")
    type: str = ""
    """One of `TEXT`, `IMAGES`, `RENAME`, `SPOND`, `INTERNAL_PROMO`,
    `CAMPAIGN` (and likely more — Spond extends this set over time;
    unknown values pass through unchanged)."""
    timestamp: datetime | None = None
    reactions: dict[str, Any] = Field(default_factory=dict)
    """Emoji-reactions map. Empty for messages without reactions."""

    # Often present — most user-sent message types carry these
    text: str | None = None
    user: str | None = None
    """Sender's profile UID. Absent on system messages (INTERNAL_PROMO,
    CAMPAIGN, etc.)."""

    # Type-specific payloads — declared so they get docs and IDE hints,
    # but each is `None` unless the message is of the matching `type`.
    new_name: str | None = Field(default=None, alias="newName")
    """Set when `type=="RENAME"` — the chat's new title."""
    images: list[Any] = Field(default_factory=list)
    """Set when `type=="IMAGES"` — attached image objects (raw)."""
    internal_promo: dict[str, Any] | None = Field(default=None, alias="internalPromo")
    """Set when `type=="INTERNAL_PROMO"` — Spond's own promotional content."""
    campaign: dict[str, Any] | None = None
    """Set when `type=="CAMPAIGN"` — community campaign payload."""
    spond: dict[str, Any] | None = None
    """Set when `type=="SPOND"` — embedded event share."""

    def _natural_key(self) -> tuple | None:
        """Messages have no `uid` — identity is `(chat_id, msg_num)`, the
        composite key Spond uses to address an individual message."""
        if self.chat_id is not None and self.msg_num is not None:
            return ("Message", self.chat_id, self.msg_num)
        return None


class Chat(DictCompatModel):
    """A chat thread — group, direct message, system channel, or campaign.

    Construct via `Spond.get_messages()` — both wire `_client` for you.
    Direct instantiation works but `chat.send(...)` will refuse to run
    without a client attached.

    Example
    -------
    ```python
    chats = await spond.get_messages()
    for chat in chats:
        if chat.unread and chat.message and chat.message.type == "TEXT":
            print(f"unread in {chat.name!r}: {chat.message.text!r}")
            await chat.send("ack")
    ```
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        arbitrary_types_allowed=True,
    )

    uid: str = Field(alias="id")
    name: str = ""
    type: str = ""
    """One of `GROUP`, `DM`, `INTERNAL_PROMO`, `CAMPAIGN` (and similar —
    unknown values pass through unchanged)."""
    participants: list[str] = Field(default_factory=list)
    """Profile UIDs of members participating in this thread."""
    newest_timestamp: datetime | None = Field(default=None, alias="newestTimestamp")
    """Timestamp of the most recent message in the thread."""
    unread: bool = False
    muted: bool = False
    community: dict[str, Any] | None = None
    """Community-channel metadata (`{type: "NONE"}` for non-community
    chats). Unmodelled — varies by chat kind."""
    message: Message | None = None
    """The most recent message in this thread — the only one the chat
    list endpoint includes. Full history isn't exposed by this SDK."""

    _client: Any = PrivateAttr(default=None)

    def __str__(self) -> str:
        return f"Chat(uid={self.uid!r}, name={self.name!r}, type={self.type!r})"

    def _natural_key(self) -> tuple | None:
        """uid when set; otherwise (name, type) for unsaved threads."""
        if self.uid:
            return ("Chat", self.uid)
        if self.name or self.type:
            return ("Chat", None, self.name, self.type)
        return None

    @classmethod
    def from_api(cls, data: dict[str, Any], client: Spond | None) -> Chat:
        """Construct a `Chat` from raw API data and bind the client.

        Used internally by `Spond.get_messages()`. Sets `_client` so the
        `send()` method can issue HTTP calls.
        """
        instance = cls.model_validate(data)
        instance._client = client
        return instance

    async def send(self, text: str) -> dict[str, Any]:
        """Post a TEXT message to this chat thread.

        Performs the lazy chat-server handshake on first call (same
        machinery `Spond.send_message` uses for the `chat_id` path).

        Parameters
        ----------
        text : str
            Message body. Spond sends it as `type=TEXT`.

        Returns
        -------
        dict
            The Spond chat API's response for the send operation.
        """
        if self._client is None:
            raise RuntimeError(
                "Chat has no client attached; instantiate via Spond.get_messages()."
            )
        if self._client._auth is None:
            await self._client._login_chat()
        payload = {"chatId": self.uid, "text": text, "type": "TEXT"}
        url = f"{self._client._chat_url}/messages"
        async with self._client.clientsession.post(
            url, json=payload, headers={"auth": self._client._auth}
        ) as r:
            return await r.json()
