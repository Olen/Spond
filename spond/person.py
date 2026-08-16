"""Typed `Person` base class with `Member` and `Guardian` subclasses.

The Spond API uses two flavours of person attached to a `Group`:

- **Member** — a person invited to events, who can respond, hold roles,
  and (for child members) have one or more guardians.
- **Guardian** — a person attached to a Member to receive notifications
  and respond on the member's behalf. Has fewer fields than Member
  (no email, no roles, no nested guardians, no `respondent` flag).

Both share a common shape (uid, name, profile, phone) which we model as
the abstract base `Person`. `Member` and `Guardian` extend it with their
respective specifics.

Construct via `Spond.get_groups()` and walk `group.members`; or via
`Spond.get_person(user)`, which can return either kind.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field, PrivateAttr

from ._compat import DictCompatModel, LenientDate


class Person(DictCompatModel):
    """Shared base for `Member` and `Guardian`.

    Carries only the fields that both flavours include (uid, names, profile,
    phone). Subclasses add their specifics. Not intended to be instantiated
    directly — use `Spond.get_person()` to obtain a Person of the right
    concrete type.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        arbitrary_types_allowed=True,
    )

    uid: str = Field(alias="id")
    # `first_name` and `last_name` are present on every member/guardian
    # we've seen in the wild, but defaulted to "" so a missing field in
    # one record can't crash the entire `get_groups()` payload.
    first_name: str = Field(default="", alias="firstName")
    last_name: str = Field(default="", alias="lastName")
    profile: dict[str, Any] | None = None
    """Profile reference dict — `{id, contactMethod, ...}`. Kept as a raw
    dict (not a typed `Profile` model) because Spond's `members[].profile`
    payload is a sparse reference, not the rich account record that
    `Spond.get_profile()` returns. The two have different shapes; modelling
    them as one type would create false equivalence."""
    phone_number: str | None = Field(default=None, alias="phoneNumber")

    # Non-serialised reference back to the Spond client for HTTP calls.
    _client: Any = PrivateAttr(default=None)

    @property
    def full_name(self) -> str:
        """Convenience: non-empty `first_name` and `last_name` joined by a
        single space. Returns `""` when both are missing (avoids the bare
        `" "` artefact when name fields default to empty strings)."""
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    def __str__(self) -> str:
        # `<unnamed>` mirrors the `"?"` sentinel used by Event/Post/Comment
        # for missing timestamps — better debug output than an empty
        # `name=''` when both first_name and last_name default to empty.
        name = self.full_name or "<unnamed>"
        return f"{self.__class__.__name__}(uid={self.uid!r}, name={name!r})"

    def _natural_key(self) -> tuple | None:
        """uid when set; otherwise full_name + email. Returns the same
        kind tag (`"Person"`) for Member and Guardian, so two records
        for the same human (one a member, one a guardian elsewhere)
        compare unequal only if their identifiers differ — matching
        Spond's data model where the same uid never appears in both
        roles for the same account."""
        if self.uid:
            return ("Person", self.uid)
        email = getattr(self, "email", None)
        if self.full_name or email:
            return ("Person", None, self.full_name, email)
        return None


class Guardian(Person):
    """A guardian attached to a `Member`.

    Guardians receive notifications about the member they care for and may
    respond to events on the member's behalf. They have a strictly smaller
    field set than Members (no `email`, no `roles`, no nested `guardians`).

    Constructed by `Group.from_api()` (via Pydantic) and wired with
    `_client` post-validation. Don't instantiate directly.
    """

    async def send_message(self, text: str, group_uid: str) -> dict[str, Any]:
        """Send a chat message directly to this guardian.

        Spond routes the message via the guardian's profile id. Requires the
        group context (`group_uid`) the guardian is reachable through.

        Returns
        -------
        dict
            The Spond chat API's response for the send operation.
        """
        return await _send_message_to_person(self, text, group_uid)


class Member(Person):
    """A member of a Group — someone who can be invited to events.

    Carries Member-specific fields (email, date of birth, roles, guardians,
    subgroup memberships) on top of the shared `Person` base.

    `model_config` is inherited from `Person` — no redeclaration needed.
    """

    email: str | None = None
    """Email address. May be absent on minor members."""

    date_of_birth: LenientDate = Field(default=None, alias="dateOfBirth")

    created_time: datetime | None = Field(default=None, alias="createdTime")

    guardians: list[Guardian] = Field(default_factory=list)
    """Guardians attached to this member. Empty for adult members."""

    role_uids: list[str] = Field(default_factory=list, alias="roles")
    """UIDs of `Role`s this member holds within the group."""

    subgroup_uids: list[str] = Field(default_factory=list, alias="subGroups")
    """UIDs of `Subgroup`s this member belongs to within the group.

    Note: the API alias here is `subGroups` (not `subGroupIds`) because
    that's the field name Spond's groups endpoint actually returns inside
    each member object. `Post.subgroup_uids` aliases `subGroupIds` for the
    same reason — Spond's posts endpoint uses a different key name for
    what is conceptually the same kind of list. The asymmetry is in the
    API, not in this SDK.
    """

    respondent: bool = False
    """Whether this member personally responds to events (False for child
    members whose guardians respond on their behalf)."""

    custom_fields: dict[str, Any] = Field(default_factory=dict, alias="fields")
    """Per-member custom fields the group admin has defined (e.g. shirt
    size, dietary requirements). Maps the API's `fields` key, but exposed
    here as `custom_fields` to avoid confusion with Pydantic's
    `model_fields` metadata vocabulary."""

    async def send_message(self, text: str, group_uid: str) -> dict[str, Any]:
        """Send a chat message directly to this member.

        Parameters
        ----------
        text : str
            Message body.
        group_uid : str
            UID of the group context the chat belongs to.

        Returns
        -------
        dict
            The Spond chat API's response for the send operation.
        """
        return await _send_message_to_person(self, text, group_uid)


async def _send_message_to_person(
    person: Person, text: str, group_uid: str
) -> dict[str, Any]:
    """Send a chat message to any Person (Member or Guardian).

    Implementation shared between `Member.send_message` and
    `Guardian.send_message` — Spond routes by the recipient's profile id,
    which is the same field on both kinds.
    """
    client = person._client
    if client is None:
        raise RuntimeError(
            f"{type(person).__name__} has no client attached; instantiate via "
            f"Spond.get_person() or walk Spond.get_groups()."
        )

    # Validate caller args BEFORE the chat-server handshake so a pure
    # client-side argument error doesn't trigger a network round-trip.
    # Mirrors the same fail-fast ordering in `Spond.send_message`.
    if not isinstance(person.profile, dict) or "id" not in person.profile:
        raise ValueError(
            f"{type(person).__name__} {person.uid} has no profile id; "
            f"Spond cannot route a message without one."
        )

    # Lazy chat handshake (Spond's chat API uses a separate host + token).
    if client._auth is None:
        await client._login_chat()

    payload = {
        "text": text,
        "type": "TEXT",
        "recipient": person.profile["id"],
        "groupId": group_uid,
    }
    url = f"{client._chat_url}/messages"
    async with client.clientsession.post(
        url, json=payload, headers={"auth": client._auth}
    ) as r:
        return await r.json()
