"""Typed `Role` model — a permission role within a `Group`.

Roles are passive data — they have no behaviour. Members reference them by
UID via `Member.role_uids`; resolve to `Role` objects by walking
`group.roles`.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from ._compat import DictCompatModel


class Role(DictCompatModel):
    """A named permission role within a `Group` (e.g. \"Coach\", \"Treasurer\")."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    uid: str = Field(alias="id")
    name: str
    permissions: list[str] = Field(default_factory=list)
    """API permission strings, e.g. `["members", "events", "posts"]`."""

    def __str__(self) -> str:
        return f"Role(uid={self.uid!r}, name={self.name!r})"
