"""Tests for the deprecated event-attendance xlsx export wrapper.

The OO-rewrite path is covered by `TestEventOOMethods` (the `Event.attendance_xlsx()`
method) — this file pins down the *backward-compat shape* of
`Spond.get_event_attendance_xlsx()` so callers on the old API surface keep
working until the deprecation cycle completes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from spond.spond import Spond

from .conftest import MOCK_PASSWORD, MOCK_USERNAME


class TestExportMethod:
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_export(self, mock_get, mock_token) -> None:
        """Deprecated `Spond.get_event_attendance_xlsx()` should still GET the
        export endpoint and return raw bytes (delegates to
        `Event.attendance_xlsx()`)."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token
        # Note: `s.events` is intentionally not pre-populated — the
        # deprecated wrapper does a direct GET on the export endpoint, it
        # doesn't consult the events cache.

        mock_binary = b"\x68\x65\x6c\x6c\x6f\x77\x6f\x72\x6c\x64"  # helloworld
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.read = AsyncMock(
            return_value=mock_binary
        )

        import warnings as _warnings

        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            data = await s.get_event_attendance_xlsx(uid="ID1")

        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
        mock_url = "https://api.spond.com/core/v1/sponds/ID1/export"
        mock_get.assert_called_once_with(
            mock_url,
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {mock_token}",
            },
        )
        assert data == mock_binary
