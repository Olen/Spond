"""Unofficial Python SDK for the Spond API.

The main entry point is `spond.spond.Spond` for general account/event/group/
messaging access, and `spond.club.SpondClub` for the Spond Club finance API.
"""

from typing import Any, TypeAlias

# Re-export the public exception surface from the dedicated module so
# `from spond import AuthenticationError` keeps working for pre-OO callers,
# and `from spond import SpondError, EventNotFoundError, ...` works for
# new callers using the typed-exception hierarchy.
from .exceptions import (
    AuthenticationError,
    ChatNotFoundError,
    EventNotFoundError,
    GroupNotFoundError,
    PersonNotFoundError,
    SpondAPIError,
    SpondError,
    SpondNotFoundError,
)

JSONDict: TypeAlias = dict[str, Any]
"""Simple alias for type hinting `dict`s that can be passed to/from JSON-handling functions."""


__all__ = [
    "AuthenticationError",
    "ChatNotFoundError",
    "EventNotFoundError",
    "GroupNotFoundError",
    "JSONDict",
    "PersonNotFoundError",
    "SpondAPIError",
    "SpondError",
    "SpondNotFoundError",
]
