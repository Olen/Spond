"""Module containing `Member` class."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from .profile_ import Profile


class Member(BaseModel):
    """Represents a member in the Spond system.

    A `Member` is an individual's `Group`-specific record.

    A `Member` may have a `Profile`.
    """

    uid: str = Field(alias="id")
    """`id` in Spond API; aliased as that's a Python built-in, and the Spond package
    uses `uid`."""
    created_time: datetime = Field(alias="createdTime")
    """Derived from `createdTime` in Spond API."""
    first_name: str = Field(alias="firstName")
    """`firstName` in Spond API."""
    last_name: str = Field(alias="lastName")
    """`lastName` in Spond API."""

    # Lists which always exist in Spond API data, but may be empty
    subgroup_uids: list[str] = Field(alias="subGroups")
    """`subGroups` in Spond API; aliased to avoid confusion with `Subgroup` instances.
    May be empty."""

    # Optional in Spond API data
    email: EmailStr | None = Field(default=None)
    """ Not always present."""
    phone_number: str | None = Field(alias="phoneNumber", default=None)
    """`phoneNumber` in Spond API.
    Not always present."""
    profile: Profile | None = None  # Availability may depend on permissions
    """Derived from `profile` in Spond API.
    Not always present."""
    role_uids: list[str] | None = Field(alias="roles", default=None)
    """`roles` in Spond API; aliased to avoid confusion with `Role` instances.
    Not always present."""

    def __str__(self) -> str:
        """Return simple human-readable description.

        Includes only key fields in custom order.
        """
        return f"Member(uid='{self.uid}', full_name='{self.full_name}', …)"

    @property
    def full_name(self) -> str:
        """Return the `Member`'s full name, for convenience."""
        return f"{self.first_name} {self.last_name}"
