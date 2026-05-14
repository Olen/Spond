"""Shared fixtures, constants, and module-import-time setup for the Spond
test suite.

pytest auto-discovers this file, so fixtures defined here (e.g. `mock_token`)
are available to every test file without explicit import. Constants and
helpers that test files need to reference directly are imported via
`from .conftest import ...`.

The `_SpondBase.require_authentication` monkey-patch must happen before any
test module is imported — `conftest.py` is the canonical place for that.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from spond.base import _SpondBase
from spond.spond import Spond

if TYPE_CHECKING:
    from spond import JSONDict


# Minimum-viable Event API payload — all required fields filled with placeholder
# data. Tests that need an Event object can spread/override.
_MIN_EVENT_PAYLOAD: dict = {
    "id": "ID1",
    "heading": "Event One",
    "startTimestamp": "2026-01-01T10:00:00Z",
    "endTimestamp": "2026-01-01T11:00:00Z",
    "createdTime": "2025-12-01T10:00:00Z",
    "type": "EVENT",
    "responses": {
        "acceptedIds": [],
        "declinedIds": [],
        "unansweredIds": [],
        "waitinglistIds": [],
        "unconfirmedIds": [],
    },
}


MOCK_USERNAME, MOCK_PASSWORD = "MOCK_USERNAME", "MOCK_PASSWORD"
MOCK_TOKEN = "MOCK_TOKEN"
MOCK_PAYLOAD = {"accepted": "false", "declineMessage": "sick cannot make it"}


# Mock the `require_authentication` decorator to bypass authentication.
# Replaces the real decorator on `_SpondBase` so every test that calls a
# decorated method skips the real auth roundtrip.
def mock_require_authentication(func):
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    return wrapper


_SpondBase.require_authentication = mock_require_authentication(Spond.get_event)


@pytest.fixture
def mock_token() -> str:
    return MOCK_TOKEN


@pytest.fixture
def mock_payload() -> JSONDict:
    return MOCK_PAYLOAD
