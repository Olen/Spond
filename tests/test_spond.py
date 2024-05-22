"""Test suite for Spond class."""

import pytest

from spond.spond import Spond

MOCK_USERNAME, MOCK_PASSWORD = "MOCK_USERNAME", "MOCK_PASSWORD"
MOCK_TOKEN = "MOCK_TOKEN"


# Mock the `require_authentication` decorator to bypass authentication
def mock_require_authentication(func):
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    return wrapper


Spond.require_authentication = mock_require_authentication(Spond.get_event)


@pytest.fixture
def mock_events():
    """Mock a minimal list of events."""
    return [
        {
            "id": "ID1",
            "name": "Event One",
        },
        {
            "id": "ID2",
            "name": "Event Two",
        },
    ]


@pytest.fixture
def mock_groups():
    """Mock a minimal list of groups."""
    return [
        {
            "id": "ID1",
            "name": "Group One",
        },
        {
            "id": "ID2",
            "name": "Group Two",
        },
    ]


@pytest.fixture
def mock_token():
    return MOCK_TOKEN


@pytest.mark.asyncio
async def test_get_event__happy_path(mock_events, mock_token):
    """Test that a valid `id` returns the matching event."""

    s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
    s.events = mock_events
    s.token = mock_token
    g = await s.get_event("ID1")

    assert g == {
        "id": "ID1",
        "name": "Event One",
    }


@pytest.mark.asyncio
async def test_get_event__no_match_raises_exception(mock_events, mock_token):
    """Test that a non-matched `id` raises IndexError."""

    s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
    s.events = mock_events
    s.token = mock_token

    with pytest.raises(IndexError):
        await s.get_event("ID3")


@pytest.mark.asyncio
async def test_get_event__blank_id_match_raises_exception(mock_events, mock_token):
    """Test that a blank `id` raises IndexError."""

    s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
    s.events = mock_events
    s.token = mock_token

    with pytest.raises(IndexError):
        await s.get_event("")


@pytest.mark.asyncio
async def test_get_group__happy_path(mock_groups, mock_token):
    """Test that a valid `id` returns the matching group."""

    s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
    s.groups = mock_groups
    s.token = mock_token
    g = await s.get_group("ID2")

    assert g == {
        "id": "ID2",
        "name": "Group Two",
    }


@pytest.mark.asyncio
async def test_get_group__no_match_raises_exception(mock_groups, mock_token):
    """Test that a non-matched `id` raises IndexError."""

    s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
    s.groups = mock_groups
    s.token = mock_token

    with pytest.raises(IndexError):
        await s.get_group("ID3")


@pytest.mark.asyncio
async def test_get_group__blank_id_raises_exception(mock_groups, mock_token):
    """Test that a blank `id` raises IndexError."""

    s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
    s.groups = mock_groups
    s.token = mock_token

    with pytest.raises(IndexError):
        await s.get_group("")
