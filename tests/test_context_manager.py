"""Tests for the `async with Spond(...)` context-manager shape.

`__aenter__` returns self; `__aexit__` closes the aiohttp ClientSession.
"""

from __future__ import annotations

import pytest

from spond.club import SpondClub
from spond.spond import Spond

from .conftest import MOCK_PASSWORD, MOCK_USERNAME


class TestSpondAsContextManager:
    @pytest.mark.asyncio
    async def test_enter_returns_self(self) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        async with s as ctx:
            assert ctx is s

    @pytest.mark.asyncio
    async def test_session_closed_on_exit(self) -> None:
        """The clientsession must be closed when the `with` block exits."""
        async with Spond(MOCK_USERNAME, MOCK_PASSWORD) as s:
            assert not s.clientsession.closed
        assert s.clientsession.closed

    @pytest.mark.asyncio
    async def test_session_closed_even_on_exception(self) -> None:
        """Cleanup must fire even when the body raises — that's the
        whole point of `async with`."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        with pytest.raises(RuntimeError, match="intentional"):
            async with s:
                raise RuntimeError("intentional")
        assert s.clientsession.closed

    @pytest.mark.asyncio
    async def test_double_close_does_not_raise(self) -> None:
        """If the caller manually closed the session inside the block,
        the context-manager exit shouldn't blow up on top of it —
        defensive cleanup must not mask the original control flow."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        async with s:
            await s.clientsession.close()
        # No exception escaped; both close paths were tolerated.

    @pytest.mark.asyncio
    async def test_spondclub_also_supports_context_manager(self) -> None:
        """Both subclasses of `_SpondBase` inherit the shape."""
        async with SpondClub(MOCK_USERNAME, MOCK_PASSWORD) as sc:
            assert not sc.clientsession.closed
        assert sc.clientsession.closed
