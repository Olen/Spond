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
        """Return the Python attribute name for a declared field matching `key`.

        Matches either the field's API alias or its Python name. Resolution
        is bounded to `self.__class__.model_fields` — never reaches parent
        attributes that aren't declared as fields. Does **not** resolve
        keys against `__pydantic_extra__`; callers wanting that should
        check `_pydantic_extras()` separately.
        """
        for field_name, field_info in self.__class__.model_fields.items():
            if field_info.alias == key or field_name == key:
                return field_name
        return None

    def _pydantic_extras(self) -> dict[str, Any]:
        """Unknown fields preserved by `model_config = extra="allow"`.

        Empty dict for models with `extra="ignore"` (the older config), since
        Pydantic discards unknown fields there.
        """
        return getattr(self, "__pydantic_extra__", None) or {}

    def _present_api_keys(self) -> list[str]:
        """API-shaped key names actually present in the source data.

        Returns declared fields that were set during validation (using
        their alias if defined, else Python name) plus any extras
        preserved via `extra="allow"`. Mirrors pre-OO dict semantics where
        iterating a parsed JSON response yielded only the keys the API
        actually sent.
        """
        keys: list[str] = []
        present_declared = set(self.model_fields_set)
        for field_name, field_info in self.__class__.model_fields.items():
            if field_name in present_declared:
                keys.append(field_info.alias or field_name)
        keys.extend(self._pydantic_extras().keys())
        return keys

    def __getitem__(self, key: str) -> Any:
        field_name = self._resolve_dict_key(key)
        if field_name is not None and field_name in self.model_fields_set:
            warnings.warn(
                f"{self.__class__.__name__}[{key!r}] uses deprecated dict-style "
                f"access; use attribute access (`.{field_name}`) instead",
                DeprecationWarning,
                stacklevel=2,
            )
            return getattr(self, field_name)
        extras = self._pydantic_extras()
        if key in extras:
            warnings.warn(
                f"{self.__class__.__name__}[{key!r}] accesses an unmodelled "
                f"field preserved via extra='allow'; dict-style access is "
                f"deprecated — use `obj.{key}` instead",
                DeprecationWarning,
                stacklevel=2,
            )
            return extras[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style `.get(key, default)` with deprecation warning."""
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        field_name = self._resolve_dict_key(key)
        if field_name is not None and field_name in self.model_fields_set:
            return True
        return key in self._pydantic_extras()

    def __iter__(self) -> Iterator[str]:  # type: ignore[override]
        """Yield API-shaped keys for fields actually present in the source data.

        Overrides `pydantic.BaseModel.__iter__` (which yields `(name, value)`
        tuples) so `for k in obj` matches dict semantics. Only yields keys
        for fields populated during validation plus any extras preserved
        via `extra="allow"` — not defaulted fields.
        """
        yield from self._present_api_keys()

    def __len__(self) -> int:
        return len(self._present_api_keys())

    def keys(self) -> list[str]:
        """Dict-style `.keys()` — API-shaped names of fields present in the source."""
        return list(self._present_api_keys())

    def values(self) -> list[Any]:
        """Dict-style `.values()` — values for fields present in the source."""
        present_declared = set(self.model_fields_set)
        result = [
            getattr(self, name)
            for name in self.__class__.model_fields
            if name in present_declared
        ]
        result.extend(self._pydantic_extras().values())
        return result

    def items(self) -> list[tuple[str, Any]]:
        """Dict-style `.items()` — (api-key, value) pairs for fields present."""
        present_declared = set(self.model_fields_set)
        result: list[tuple[str, Any]] = []
        for field_name, field_info in self.__class__.model_fields.items():
            if field_name in present_declared:
                key = field_info.alias or field_name
                result.append((key, getattr(self, field_name)))
        for extra_key, extra_value in self._pydantic_extras().items():
            result.append((extra_key, extra_value))
        return result

    # -----------------------------------------------------------------
    # Identity / equality / hashing
    #
    # Pydantic's default `__eq__` compares every field; two `Event`
    # instances with the same `uid` but slightly different (e.g.
    # `updated`) state are considered different. That's the wrong
    # semantics for entity types served by a remote API — most callers
    # want "same uid → same entity", and want to use Event instances as
    # set members or dict keys.
    #
    # `_natural_key()` is the override hook. Subclasses return a tuple
    # of (entity_kind, *identifying_fields). The default uses
    # `(class-tree-root.__name__, uid)` when uid is set so `Match("X")`
    # and `Event("X")` are equal (Match's MRO walks back to Event).
    # When uid is absent (a freshly-constructed instance not yet
    # persisted), subclasses provide a fallback natural key derived
    # from user-visible fields (e.g. heading + start_time for Event).
    # Returning `None` falls back to Pydantic's full-field equality.
    # -----------------------------------------------------------------

    def _natural_key(self) -> tuple | None:
        """Return a tuple uniquely identifying this entity, or `None` to
        fall back to Pydantic's full-field equality.

        Default implementation: if the instance has a non-empty `uid`,
        the key is `(top-level entity class name, uid)`. This makes
        `Match(uid="X") == Event(uid="X")` evaluate True — a sensible
        outcome since they refer to the same Spond record.

        Subclasses override to provide a natural key for instances
        without a uid yet (e.g. an `Event` about to be created):

        ```python
        def _natural_key(self) -> tuple | None:
            if self.uid:
                return ("Event", self.uid)
            if self.heading or self.start_time:
                return ("Event", None, self.heading, self.start_time)
            return None
        ```
        """
        uid = getattr(self, "uid", None)
        if uid:
            return (_entity_kind_of(type(self)), uid)
        return None

    def __eq__(self, other: object) -> bool:
        # Falls outside the typed-model graph — let Python try the
        # other operand's __eq__ via NotImplemented.
        if not isinstance(other, DictCompatModel):
            return NotImplemented
        a = self._natural_key()
        b = other._natural_key()
        if a is not None and b is not None:
            return a == b
        # One or both lack a natural key — fall back to Pydantic's
        # full-field equality, but only between same-class instances
        # (cross-class full-field equality is rarely meaningful).
        if type(self) is not type(other):
            return False
        return BaseModel.__eq__(self, other)

    def __hash__(self) -> int:
        key = self._natural_key()
        if key is not None:
            return hash(key)
        # No natural key (e.g. partially-constructed instance) — fall
        # back to identity-based hash so the object is at least
        # hashable. Two such instances are unequal under __eq__'s
        # full-field-fallback path anyway, so this preserves the
        # equality/hash invariant.
        return object.__hash__(self)


def _entity_kind_of(cls: type) -> str:
    """Walk the MRO to find the nearest non-`DictCompatModel`,
    non-`BaseModel` ancestor — that's the "entity kind."

    For `Match` (which inherits from `Event`), this returns `"Event"`
    so `Match` and `Event` instances with the same uid compare equal.
    For `Member`/`Guardian` (both inheriting from `Person`), this
    returns `"Person"` for the same reason.
    """
    for ancestor in cls.__mro__:
        if ancestor is DictCompatModel or ancestor is BaseModel:
            break
        # The most-derived "non-base" class with a name is the entity
        # kind. We walk further up to find the most general one.
    # Find the top-most user-defined class in the MRO before DictCompatModel.
    user_classes = [
        c
        for c in cls.__mro__
        if c not in (DictCompatModel, BaseModel, object)
        and c.__module__.startswith("spond")
    ]
    if not user_classes:
        return cls.__name__
    # The last one in MRO before DictCompatModel is the root entity kind.
    return user_classes[-1].__name__
