"""Typed `Group` model with `find_member()` helper.

A `Group` is a Spond group the authenticated user belongs to. Each group
carries lists of `Member`s, `Subgroup`s, and `Role`s — all materialised as
their respective typed objects when the Group is constructed via
`Group.from_api()`.
"""

from __future__ import annotations

from datetime import datetime
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

    # Fields observed in the live API but absent from the original Spond
    # SDK's reverse-engineered shape. Most are admin-relevant metadata
    # (permissions, contact policy, address layout); all are optional so a
    # future field-drop doesn't crash get_groups().
    created_time: datetime | None = Field(default=None, alias="createdTime")
    member_permissions: list[str] = Field(
        default_factory=list, alias="memberPermissions"
    )
    """Permission strings granted to regular members (e.g. `["posts"]`)."""
    guardian_permissions: list[str] = Field(
        default_factory=list, alias="guardianPermissions"
    )
    """Permission strings granted to guardians (e.g. `["posts"]`)."""
    membership_requests: list[dict[str, Any]] = Field(
        default_factory=list, alias="membershipRequests"
    )
    """Pending join requests. Each entry is unmodelled."""
    chat_age_limit: int | None = Field(default=None, alias="chatAgeLimit")
    """Minimum age allowed in group chats."""
    share_contact_info: bool = Field(default=False, alias="shareContactInfo")
    """Whether member contact info is visible to other members."""
    contact_info_hidden: bool = Field(default=False, alias="contactInfoHidden")
    admins_can_add_members: bool = Field(default=False, alias="adminsCanAddMembers")
    address_format: list[str] = Field(default_factory=list, alias="addressFormat")
    """Field-order hint for displaying member addresses, e.g.
    `["street", "zip", "city"]`."""
    allow_sms_nag: bool = Field(default=False, alias="allowSmsNag")
    bonus_enabled: bool = Field(default=False, alias="bonusEnabled")
    invited_to_app_time: datetime | None = Field(default=None, alias="invitedToAppTime")

    # Less user-facing — admin/finance internals. Kept as raw containers
    # because their nested shapes vary by Spond Club configuration and
    # we don't want to over-promise a structure.
    field_defs: list[Any] = Field(default_factory=list, alias="fieldDefs")
    """Custom-field definitions configured on the group. Unmodelled."""
    default_fields: dict[str, Any] = Field(default_factory=dict, alias="defaultFields")
    """Default per-member field metadata. Unmodelled."""
    payout_accounts: list[Any] = Field(default_factory=list, alias="payoutAccounts")
    """Spond Club payout accounts attached to the group."""
    allow_private_payout_accounts: bool = Field(
        default=False, alias="allowPrivatePayoutAccounts"
    )
    experiments: dict[str, Any] = Field(default_factory=dict)
    """A/B experiment flags Spond has enabled for this group. Internal."""

    _client: Any = PrivateAttr(default=None)

    def __str__(self) -> str:
        return (
            f"Group(uid={self.uid!r}, name={self.name!r}, members={len(self.members)})"
        )

    def _natural_key(self) -> tuple | None:
        """uid when set; otherwise the group `name` distinguishes
        unsaved groups."""
        if self.uid:
            return ("Group", self.uid)
        if self.name:
            return ("Group", None, self.name)
        return None

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
            Match against `member.full_name` (exact). Note: `full_name`
            joins only non-empty parts, so a member whose record carries
            only `firstName` (no last name) has `full_name == "Alice"`,
            not `"Alice "`. Pass the trimmed form.

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
