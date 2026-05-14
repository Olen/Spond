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

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict, Field, PrivateAttr

from ._compat import DictCompatModel

if TYPE_CHECKING:
    from .spond import Spond


class Person(DictCompatModel):
    """Shared base for `Member` and `Guardian`.

    Carries only the fields that both flavours include (uid, names, profile,
    phone). Subclasses add their specifics. Not intended to be instantiated
    directly — use `Spond.get_person()` to obtain a Person of the right
    concrete type.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        arbitrary_types_allowed=True,
    )

    uid: str = Field(alias="id")
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    profile: dict[str, Any] | None = None
    """Profile reference dict — `{id, contactMethod, ...}`. Unmodelled for now;
    use `Spond.get_profile()` to fetch the full profile of the authenticated
    user."""
    phone_number: str | None = Field(default=None, alias="phoneNumber")

    # Non-serialised reference back to the Spond client for HTTP calls.
    _client: Any = PrivateAttr(default=None)

    @property
    def full_name(self) -> str:
        """Convenience: `first_name` + ` ` + `last_name`."""
        return f"{self.first_name} {self.last_name}"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(uid={self.uid!r}, name={self.full_name!r})"


class Guardian(Person):
    """A guardian attached to a `Member`.

    Guardians receive notifications about the member they care for and may
    respond to events on the member's behalf. They have a strictly smaller
    field set than Members (no `email`, no `roles`, no nested `guardians`).
    """

    @classmethod
    def from_api(cls, data: dict[str, Any], client: Spond | None) -> Guardian:
        instance = cls.model_validate(data)
        instance._client = client
        return instance

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
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        arbitrary_types_allowed=True,
    )

    email: str | None = None
    """Email address. May be absent on minor members."""

    date_of_birth: date | None = Field(default=None, alias="dateOfBirth")

    created_time: datetime | None = Field(default=None, alias="createdTime")

    guardians: list[Guardian] = Field(default_factory=list)
    """Guardians attached to this member. Empty for adult members."""

    role_uids: list[str] = Field(default_factory=list, alias="roles")
    """UIDs of `Role`s this member holds within the group."""

    subgroup_uids: list[str] = Field(default_factory=list, alias="subGroups")
    """UIDs of `Subgroup`s this member belongs to within the group."""

    respondent: bool = False
    """Whether this member personally responds to events (False for child
    members whose guardians respond on their behalf)."""

    fields: dict[str, Any] = Field(default_factory=dict)
    """Custom fields defined on the group. Unmodelled for now."""

    @classmethod
    def from_api(cls, data: dict[str, Any], client: Spond | None) -> Member:
        instance = cls.model_validate(data)
        instance._client = client
        # Wire client into nested Guardians too
        for g in instance.guardians:
            g._client = client
        return instance

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

    # Lazy chat handshake (Spond's chat API uses a separate host + token).
    if client._auth is None:
        await client._login_chat()

    if person.profile is None or "id" not in person.profile:
        raise ValueError(
            f"{type(person).__name__} {person.uid} has no profile id; "
            f"Spond cannot route a message without one."
        )

    payload = {
        "text": text,
        "type": "TEXT",
        "recipient": person.profile["id"],
        "groupId": group_uid,
    }
    url = f"{client._chat_url}/messages"
    r = await client.clientsession.post(
        url, json=payload, headers={"auth": client._auth}
    )
    return await r.json()
