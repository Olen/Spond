"""Module containing `Subgroup` class."""

from pydantic import BaseModel, Field


class Subgroup(BaseModel):
    """Represents a subgroup in the Spond system.

    A `Subgroup` belongs to a `Group`.

    Use `Group.members_by_subgroup()` to get subordinate `Member`s.
    """

    uid: str = Field(alias="id")
    """`id` in Spond API; aliased as that's a Python built-in, and the Spond package
    uses `uid`."""
    name: str

    def __str__(self) -> str:
        """Return simple human-readable description."""
        return f"Subgroup(uid='{self.uid}', name='{self.name}')"
