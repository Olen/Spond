"""Module containing `Profile` class."""

from pydantic import BaseModel, EmailStr, Field


class Profile(BaseModel):
    """Represents a profile in the Spond system.

    A `Profile` is an individual's account-specific record.

    A `Profile` belongs to a `Member`.
    """

    uid: str = Field(alias="id")
    """`id` in Spond API; aliased as that's a Python built-in, and the Spond package
    uses `uid`."""
    first_name: str = Field(alias="firstName")
    """`firstName` in Spond API."""
    last_name: str = Field(alias="lastName")
    """`lastName` in Spond API."""

    # Optional in Spond API data
    email: EmailStr | None = Field(default=None)
    """Not always present."""
    phone_number: str | None = Field(alias="phoneNumber", default=None)
    """`phoneNumber` in Spond API.
    Not always present."""

    def __str__(self) -> str:
        """Return simple human-readable description.

        Includes only key fields in custom order.
        """
        return f"Profile(uid='{self.uid}', full_name='{self.full_name}', …)"

    @property
    def full_name(self) -> str:
        """Return the `Profile`'s full name, for convenience."""
        return f"{self.first_name} {self.last_name}"
