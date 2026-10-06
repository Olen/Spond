"""Shared fixtures and constants for the Spond test suite.

pytest auto-discovers this file, so fixtures defined here (e.g. `mock_token`)
are available to every test file without explicit import. Constants that
test files need to reference directly are imported via
`from .conftest import ...`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

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


# Authentication is bypassed by setting `s.token = mock_token` on every test
# `Spond` instance before invoking a decorated method. The real
# `require_authentication` decorator then short-circuits its `if not
# self.token: await self.login()` check without issuing HTTP. No
# class-level monkey-patch is needed (and wouldn't work anyway —
# `@_SpondBase.require_authentication` is applied at class-definition
# time, so reassigning the attribute later doesn't re-decorate methods).


@pytest.fixture
def mock_token() -> str:
    return MOCK_TOKEN


@pytest.fixture
def mock_payload() -> JSONDict:
    return MOCK_PAYLOAD
