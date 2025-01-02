"""Module containing `Role` class."""

from pydantic import BaseModel, Field


class Role(BaseModel):
    """Represents a role in the Spond system.

    A `Role` belongs to a `Group`.

    Use `Group.members_by_role()` to get subordinate `Member`s.
    """

    uid: str = Field(alias="id")
    """`id` in Spond API; aliased as that's a Python built-in, and the Spond package
    uses `uid`."""
    name: str

    def __str__(self) -> str:
        """Return simple human-readable description."""
        return f"Role(uid='{self.uid}', name='{self.name}')"
