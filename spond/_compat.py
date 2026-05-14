"""Internal helpers for backward-compatible dict-style access on typed models.

The pre-OO public API returned raw `dict[str, Any]` from every `get_*` method.
The OO rewrite returns Pydantic models instead. To avoid breaking existing
callers that subscript the result (`event["heading"]`, `event.get("id")`,
`"heading" in event`, …), every typed model inherits from `DictCompatModel`,
which adds dict-style read access.

A `DeprecationWarning` is emitted from `__getitem__` and `get()` so callers
can find their dict-style sites and migrate to attribute access. The other
dict-compat surface (`__iter__`, `keys`, `values`, `items`, `__len__`,
`__contains__`) does not warn — it's noisier and provides less signal.

Mutation via subscript is intentionally not supported: the typed models are
read-only at the dict-compat layer, and writes go through the ActiveRecord
methods on each type (`event.update(...)`, `event.change_response(...)`, …).
"""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator


def _parse_date_lenient(value: Any) -> date | None:
    """Parse a date string tolerantly — return `None` for unparseable input.

    Spond's API occasionally returns malformed `dateOfBirth` values (e.g.
    `'2012-03-99'` with an impossible day). Strict ISO-8601 parsing would
    raise; we want callers to keep working with `None` for that field.
    """
    if value is None or isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


LenientDate = Annotated[date | None, BeforeValidator(_parse_date_lenient)]
"""Type alias for `dateOfBirth`-shaped fields that may contain malformed data.

Use this in place of `date | None` for any field where Spond's API has been
observed to return values that fail strict ISO-8601 parsing. Unparseable
values become `None` rather than raising `ValidationError`.
"""


class DictCompatModel(BaseModel):
    """Pydantic base class with dict-style read access for backward compatibility.

    Subscript access (`obj["key"]`) maps either the API-side camelCase alias or
    the Python-side snake_case attribute name to the underlying attribute,
    emitting a `DeprecationWarning` so callers are nudged toward attribute
    access. Other dict-style operations work without warning.

    Subclasses should inherit from this instead of directly from
    `pydantic.BaseModel`.
    """

    def _resolve_dict_key(self, key: str) -> str | None:
        """Return the Python attribute name matching `key`, or None.

        Matches either the field's API alias or its Python name.
        """
        for field_name, field_info in self.__class__.model_fields.items():
            if field_info.alias == key or field_name == key:
                return field_name
        return None

    def __getitem__(self, key: str) -> Any:
        field_name = self._resolve_dict_key(key)
        if field_name is None:
            raise KeyError(key)
        warnings.warn(
            f"{self.__class__.__name__}[{key!r}] uses deprecated dict-style "
            f"access; use attribute access (`.{field_name}`) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(self, field_name)

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style `.get(key, default)` with deprecation warning."""
        field_name = self._resolve_dict_key(key)
        if field_name is None:
            return default
        warnings.warn(
            f"{self.__class__.__name__}.get({key!r}) uses deprecated dict-style "
            f"access; use attribute access (`.{field_name}`) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(self, field_name)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self._resolve_dict_key(key) is not None

    def __iter__(self) -> Iterator[str]:  # type: ignore[override]
        """Yield API-shaped keys (alias if defined, else field name).

        This deliberately overrides `pydantic.BaseModel.__iter__`, which yields
        `(name, value)` tuples — dict-compat callers expect just the keys.
        """
        for field_name, field_info in self.__class__.model_fields.items():
            yield field_info.alias or field_name

    def __len__(self) -> int:
        return len(self.__class__.model_fields)

    def keys(self) -> list[str]:
        """Dict-style `.keys()` — returns the API-shaped key names."""
        return list(iter(self))

    def values(self) -> list[Any]:
        """Dict-style `.values()` — returns the attribute values in field order."""
        return [getattr(self, name) for name in self.__class__.model_fields]

    def items(self) -> list[tuple[str, Any]]:
        """Dict-style `.items()` — returns (api-key, value) pairs in field order."""
        result = []
        for field_name, field_info in self.__class__.model_fields.items():
            key = field_info.alias or field_name
            result.append((key, getattr(self, field_name)))
        return result
