"""Typed `FieldDef` model — definitions for the custom fields a Group exposes
on its members.

Spond's `Group.fieldDefs` is a list of definitions describing the
custom-data slots each member can fill (e.g. `"shirt size"`,
`"emergency contact"`). The per-member values live on
`Member.custom_fields` as a `dict` keyed by the field-def uid; this
class gives those keys human-readable context:

```python
for fd in group.field_defs:
    value = member.custom_fields.get(fd.uid)
    print(f"{fd.name}: {value}")
```

The model is intentionally minimal — Spond's API may carry additional
fields per definition (type, required-flag, ordering hints), but those
shapes vary by Spond release and aren't part of the SDK contract.
`extra="allow"` preserves them on the instance for callers who need
to reach in directly.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from ._compat import DictCompatModel


class FieldDef(DictCompatModel):
    """A custom-field definition attached to a `Group`."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    uid: str = Field(alias="id")
    name: str = ""
    """Human-readable label for the field, as shown in the Spond UI."""

    def __str__(self) -> str:
        return f"FieldDef(uid={self.uid!r}, name={self.name!r})"

    def _natural_key(self) -> tuple | None:
        if self.uid:
            return ("FieldDef", self.uid)
        if self.name:
            return ("FieldDef", None, self.name)
        return None
