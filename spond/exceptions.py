"""Exception hierarchy for the Spond SDK.

All SDK-raised exceptions descend from `SpondError`, so callers can
`except SpondError:` to catch anything the SDK might raise without
having to enumerate the specific subclasses.

Lookup failures (`EventNotFoundError`, `GroupNotFoundError`,
`PersonNotFoundError`, `ChatNotFoundError`) additionally inherit from
the stdlib `KeyError` so pre-OO callers that wrote `except KeyError:`
keep working through the v1.x deprecation cycle without modification.

`AuthenticationError` is re-exported from `spond.__init__` for
backward compatibility — older code imports it as `from spond import
AuthenticationError`.
"""

from __future__ import annotations


class SpondError(Exception):
    """Base class for every exception raised by this SDK.

    Catch this to handle any SDK-originated failure without naming the
    specific subclass.
    """


class AuthenticationError(SpondError):
    """Raised when login to the Spond API fails.

    Typical causes:

    - Incorrect username/password.
    - 2FA enabled on the account (the library does not currently support
      Spond's TOTP flow).
    - The account has hit Spond's login rate limit (`outOfLoginAttempts`).
    - The Spond login API has changed shape and the response no longer
      contains an `accessToken`.

    The exception message includes any of the response's whitelisted
    diagnostic fields (`error`, `errorKey`, `errorCode`, `message`) so
    most error cases are self-explanatory. Other response fields — such
    as 2FA challenge tokens and (masked) `phoneNumber` — are intentionally
    dropped from the message to avoid leaking them into application logs.
    """


class SpondAPIError(SpondError, ValueError):
    """Raised when the Spond API returns a non-success HTTP status.

    Carries the HTTP status code and the response body (truncated) so
    callers can branch on either.

    Multi-inherits from `ValueError` so pre-OO callers that wrote
    `except ValueError:` against the previous `raise ValueError(...)`
    on HTTP failure keep working through the v1.x deprecation cycle.
    New callers should use `except SpondAPIError:` and read
    `.status` / `.body` / `.url` directly.
    """

    def __init__(self, status: int, body: str = "", url: str | None = None) -> None:
        self.status = status
        self.body = body
        self.url = url
        # Truncate body in the message to keep log noise bounded
        # (the full body is still available on `self.body`).
        trimmed = body[:500] + ("…" if len(body) > 500 else "")
        # Preserve the pre-OO `ValueError` message shape so callers
        # matching on substring (e.g. `match="401"`) still work.
        if body:
            msg = f"Request failed with status {status}: {trimmed}"
        else:
            msg = f"Spond API returned HTTP {status}"
        # URL is always appended when present — it's the most useful
        # diagnostic field after the status code and is omitting it
        # silently on the body-present path made the body+url case
        # less debuggable than the body-only case.
        if url:
            msg += f" for {url}"
        super().__init__(msg)


class SpondNotFoundError(SpondError, KeyError):
    """Base for "lookup-by-id failed" errors.

    Multi-inherits from `KeyError` so existing `except KeyError:` callers
    written against the pre-OO dict-shaped API keep working unchanged.
    Catch `SpondNotFoundError` for the typed form, or `KeyError` for the
    permissive form.
    """


class EventNotFoundError(SpondNotFoundError):
    """Raised by `Spond.get_event(uid)` when no event with the given uid
    exists in the cache (and a refresh didn't surface one either)."""


class GroupNotFoundError(SpondNotFoundError):
    """Raised by `Spond.get_group(uid)` when no group with the given uid
    exists in the cache."""


class PersonNotFoundError(SpondNotFoundError):
    """Raised by `Spond.get_person(identifier)` when no member or guardian
    matches the identifier across any of the authenticated user's groups."""


class ChatNotFoundError(SpondNotFoundError):
    """Raised by chat-list lookups when no chat with the given uid exists.

    Reserved for the future `Spond.get_chat(uid)` shape; the current
    `get_messages()` returns a list and doesn't look up by uid.
    """
