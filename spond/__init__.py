"""Unofficial Python SDK for the Spond API.

The main entry point is `spond.spond.Spond` for general account/event/group/
messaging access, and `spond.club.SpondClub` for the Spond Club finance API.
"""

from typing import Any, TypeAlias

JSONDict: TypeAlias = dict[str, Any]
"""Simple alias for type hinting `dict`s that can be passed to/from JSON-handling functions."""


class AuthenticationError(Exception):
    """Raised when login to the Spond API fails.

    Typical causes:

    - Incorrect username/password.
    - 2FA enabled on the account (the library does not currently support
      Spond's TOTP flow — see #205).
    - The account has hit Spond's login rate limit (`outOfLoginAttempts`).
    - The Spond login API has changed shape and the response no longer
      contains an `accessToken`.

    The exception message includes any of the response's whitelisted
    diagnostic fields (`error`, `errorKey`, `errorCode`, `message`) so
    most error cases are self-explanatory. Other response fields — such
    as 2FA challenge tokens and (masked) `phoneNumber` — are intentionally
    dropped from the message to avoid leaking them into application logs.
    """

    pass
