from typing import Any, TypeAlias

JSONDict: TypeAlias = dict[str, Any]
"""Simple alias for type hinting `dict`s that can be passed to/from JSON-handling functions."""


class AuthenticationError(Exception):
    """Error raised on Spond authentication failure."""

    pass
