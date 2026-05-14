"""Unofficial Python SDK for the Spond API.

The main entry point is `spond.spond.Spond` for general account/event/group/
messaging access, and `spond.club.SpondClub` for the Spond Club finance API.
"""

from typing import Any, TypeAlias

JSONDict: TypeAlias = dict[str, Any]
"""Simple alias for type hinting `dict`s that can be passed to/from JSON-handling functions."""


class AuthenticationError(Exception):
    """Error raised on Spond authentication failure."""

    pass
