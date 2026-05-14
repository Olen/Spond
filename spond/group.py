"""Typed `Group` model with `find_member()` helper.

A `Group` is a Spond group the authenticated user belongs to. Each group
carries lists of `Member`s, `Subgroup`s, and `Role`s — all materialised as
their respective typed objects when the Group is constructed via
`Group.from_api()`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict, Field, PrivateAttr

from ._compat import DictCompatModel
from .person import Member
from .role import Role
from .subgroup import Subgroup

if TYPE_CHECKING:
    from .spond import Spond


class Group(DictCompatModel):
    """A Spond group, with its members, subgroups, and roles as typed lists.

    Construct via `Spond.get_group(uid)` or as elements of
    `Spond.get_groups()`. Direct instantiation works but won't attach a
    `_client` reference (which Member.send_message and other behaviour
    methods on contained objects need).

    Example
    -------
    ```python
    group = await spond.get_group(uid)
    print(group.name)
    for member in group.members:
        print(f"  {member.full_name}")
        for guardian in member.guardians:
            print(f"    guardian: {guardian.full_name}")

    coach = group.find_member(name="Ola Thoresen")
    if coach is not None:
        await coach.send_message("Practice cancelled", group_uid=group.uid)
    ```
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        arbitrary_types_allowed=True,
    )

    uid: str = Field(alias="id")
    name: str = ""
    activity: str | None = None
    """The group's sport/activity tag, e.g. `"football"`."""

    members: list[Member] = Field(default_factory=list)
    """Members of the group. Each member's nested `guardians` are typed too."""

    subgroups: list[Subgroup] = Field(default_factory=list, alias="subGroups")
    roles: list[Role] = Field(default_factory=list)

    contact_person: dict[str, Any] | None = Field(default=None, alias="contactPerson")
    """Profile reference dict for the group's primary contact. Unmodelled."""

    age_group: str | None = Field(default=None, alias="ageGroup")
    organization_type: str | None = Field(default=None, alias="organizationType")
    event_visibility: str | None = Field(default=None, alias="eventVisibility")
    country_code: str | None = Field(default=None, alias="countryCode")
    type: int | None = None

    _client: Any = PrivateAttr(default=None)

    def __str__(self) -> str:
        return (
            f"Group(uid={self.uid!r}, name={self.name!r}, members={len(self.members)})"
        )

    @classmethod
    def from_api(cls, data: dict[str, Any], client: Spond) -> Group:
        """Construct a `Group` from raw API data and wire `_client` through.

        Sets `_client` on the group and on every nested member and guardian,
        so per-instance methods like `member.send_message(...)` can issue
        HTTP calls without further plumbing. `client` is required — passing
        a no-client Group around would crash any subsequent behaviour call
        with a confusing late-stage error.
        """
        instance = cls.model_validate(data)
        instance._client = client
        for member in instance.members:
            member._client = client
            for guardian in member.guardians:
                guardian._client = client
        return instance

    def find_member(
        self,
        *,
        uid: str | None = None,
        email: str | None = None,
        name: str | None = None,
    ) -> Member | None:
        """Find a single member by uid, email, or full name.

        Exactly one of `uid`, `email`, `name` must be provided. Returns the
        first match in `self.members`, or `None` if no member matches.

        For full-name matching, `name` is compared against
        `member.full_name` (first + space + last).

        Parameters
        ----------
        uid : str, optional
            Match against `member.uid`.
        email : str, optional
            Match against `member.email` (exact).
        name : str, optional
            Match against `member.full_name` (exact).

        Returns
        -------
        Member or None

        Raises
        ------
        ValueError
            Zero or more than one search criterion was supplied.
        """
        criteria = {"uid": uid, "email": email, "name": name}
        supplied = [k for k, v in criteria.items() if v is not None]
        if len(supplied) != 1:
            raise ValueError(
                f"find_member requires exactly one of uid/email/name; got {supplied}"
            )

        for member in self.members:
            if uid is not None and member.uid == uid:
                return member
            if email is not None and member.email == email:
                return member
            if name is not None and member.full_name == name:
                return member
        return None
