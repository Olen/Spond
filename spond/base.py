"""Shared base class for Spond API clients.

`_SpondBase` is the abstract parent of both `spond.spond.Spond` (consumer API)
and `spond.club.SpondClub` (Spond Club finance API). It owns the credentials,
the underlying aiohttp `ClientSession`, the access token, and the lazy login
flow used by the `require_authentication` decorator.

Not intended to be instantiated directly — use a subclass.
"""

import functools
from abc import ABC
from collections.abc import Callable

import aiohttp

from spond import AuthenticationError

# Fields from a login response that are safe to surface in an
# `AuthenticationError` message. Anything outside this set (notably 2FA
# challenge tokens and `phoneNumber`) is dropped to avoid leaking
# sensitive data into application logs.
_SAFE_LOGIN_ERROR_FIELDS = ("error", "errorKey", "errorCode", "message")


class _SpondBase(ABC):
    """Abstract base for Spond API clients.

    Subclasses provide the API base URL via the third constructor argument
    and inherit lazy authentication, the `auth_headers` property, the
    `require_authentication` decorator, and the `login()` flow.
    """

    def __init__(self, username: str, password: str, api_url: str) -> None:
        """Initialise credentials and open the aiohttp session.

        Parameters
        ----------
        username : str
            Spond account email address.
        password : str
            Spond account password.
        api_url : str
            Base URL for the API family this client targets (consumer or
            club). Must end with a trailing slash so relative paths can be
            concatenated.
        """
        self.username = username
        self.password = password
        self.api_url = api_url
        # Use ThreadedResolver explicitly instead of aiohttp's c-ares default:
        # c-ares allocates a kernel resource (an "AresChannel") per resolver
        # instance, and the OS has a hard limit on those. A long-running
        # process or a wide test matrix that constructs many short-lived
        # `Spond` instances would otherwise hit
        # `pycares.AresError: Failed to initialize c-ares channel`.
        # ThreadedResolver uses the stdlib synchronous resolver in a thread
        # — slightly higher per-lookup overhead, no channel limit.
        self.clientsession = aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(),
            connector=aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver()),
        )
        self.token = None

    async def __aenter__(self):
        """Async context-manager entry — returns self.

        Enables the idiomatic `async with Spond(...) as s:` shape so the
        underlying aiohttp session is closed cleanly on exit, even if the
        body raises:

        ```python
        async with Spond(username, password) as s:
            events = await s.get_events()
        # session closed automatically here
        ```

        Replaces the older `await s.clientsession.close()` cleanup that
        every example used to require.
        """
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """Async context-manager exit — close the aiohttp client session.

        Checks `clientsession.closed` first so a caller who manually
        closed the session inside the `with` block doesn't trigger a
        second close. Any genuine `RuntimeError` from `close()` (resource
        leak, connector failure, etc.) is allowed to propagate rather
        than being silently swallowed — that surface signals a real bug.
        """
        if not self.clientsession.closed:
            await self.clientsession.close()

    @property
    def auth_headers(self) -> dict:
        """Headers required for authenticated requests: JSON content-type plus
        a Bearer token from `self.token`."""
        return {
            "content-type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

    @staticmethod
    def require_authentication(func: Callable):
        """Decorator that calls `self.login()` before invoking `func` if the
        client is not yet authenticated. On `AuthenticationError`, closes the
        underlying aiohttp session before re-raising."""

        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            await self._ensure_authenticated()
            return await func(self, *args, **kwargs)

        return wrapper

    async def _ensure_authenticated(self) -> None:
        """Trigger `login()` if not yet authenticated.

        Internal helper shared between the `@require_authentication`
        decorator (which wraps `Spond.*` methods) and the per-instance
        ActiveRecord methods on typed models (`event.save()`,
        `post.save()`, etc.) — those route HTTP through `self._client`
        but aren't themselves decorated, so they need to trigger the
        lazy login themselves.

        On `AuthenticationError`, closes the underlying aiohttp session
        before re-raising — same shape as the wrapper.
        """
        if not self.token:
            try:
                await self.login()
            except AuthenticationError:
                await self.clientsession.close()
                raise

    async def login(self) -> None:
        """Authenticate against the Spond API and store the access token on
        `self.token`. Called automatically by the `require_authentication`
        decorator; rarely needs to be called explicitly.

        Raises
        ------
        AuthenticationError
            If the server response does not include a usable access token.
        """
        login_url = f"{self.api_url}auth2/login"
        data = {"email": self.username, "password": self.password}
        async with self.clientsession.post(login_url, json=data) as r:
            login_result = await r.json()
        self.token = self._extract_access_token(login_result)

    @staticmethod
    def _extract_access_token(login_result: dict) -> str:
        """Pull the access-token string out of a `/auth2/login` response.

        The response shape is
        `{"accessToken": {"token": "<JWT>", "expiration": "..."}, ...}`.
        This helper validates that shape and returns the bearer string used
        for subsequent API calls.

        Parameters
        ----------
        login_result : dict
            Parsed JSON body from the login endpoint.

        Returns
        -------
        str
            The bearer-token string.

        Raises
        ------
        AuthenticationError
            The response is malformed or doesn't carry a usable token (e.g.
            wrong credentials, account locked, 2FA required).
        """
        access = login_result.get("accessToken")
        if isinstance(access, dict):
            token = access.get("token")
            if isinstance(token, str) and token:
                return token
        safe = {
            k: login_result[k] for k in _SAFE_LOGIN_ERROR_FIELDS if k in login_result
        }
        diagnostic = safe or "(no recognised diagnostic fields in response)"
        raise AuthenticationError(f"Login failed. {diagnostic}")
