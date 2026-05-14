"""Shared base class for Spond API clients.

`_SpondBase` is the abstract parent of both `spond.spond.Spond` (consumer API)
and `spond.club.SpondClub` (Spond Club finance API). It owns the credentials,
the underlying aiohttp `ClientSession`, the access token, and the lazy login
flow used by the `require_authentication` decorator.

Not intended to be instantiated directly — use a subclass.
"""

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
        self.clientsession = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
        self.token = None

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

        async def wrapper(self, *args, **kwargs):
            if not self.token:
                try:
                    await self.login()
                except AuthenticationError as e:
                    await self.clientsession.close()
                    raise e
            return await func(self, *args, **kwargs)

        return wrapper

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
