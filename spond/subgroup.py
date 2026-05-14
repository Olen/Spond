"""Typed `Subgroup` model — a sub-division of a `Group`.

Subgroups are passive data — they have no behaviour of their own. Surface
them via `group.subgroups`.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from ._compat import DictCompatModel


class Subgroup(DictCompatModel):
    """A sub-division within a `Group` (e.g. a team within a club).

    Members reference subgroups by UID via `Member.subgroup_uids`.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    uid: str = Field(alias="id")
    name: str = ""
    color: str | None = None
    image_url: str | None = Field(default=None, alias="imageUrl")

    def __str__(self) -> str:
        return f"Subgroup(uid={self.uid!r}, name={self.name!r})"

    def _natural_key(self) -> tuple | None:
        if self.uid:
            return ("Subgroup", self.uid)
        if self.name:
            return ("Subgroup", None, self.name)
        return None
