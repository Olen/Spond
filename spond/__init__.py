import sys
from typing import Any, Dict

if sys.version_info < (3, 10):
    from typing_extensions import TypeAlias
else:
    from typing import TypeAlias

from .event import Event, EventType, Responses
from .group import Group
from .member import Member
from .profile_ import Profile
from .role import Role
from .subgroup import Subgroup

__all__ = [
    "Event",
    "EventType",
    "Responses",
    "Group",
    "Member",
    "Profile",
    "Role",
    "Subgroup",
]

JSONDict: TypeAlias = Dict[str, Any]
"""Simple alias for type hinting `dict`s that can be passed to/from JSON-handling functions."""


class AuthenticationError(Exception):
    """Error raised on Spond authentication failure."""

    pass
