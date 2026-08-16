"""Tests for the Spond Club finance API — `Transaction` model and
`SpondClub.get_transactions()` pagination."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from spond.club import SpondClub, Transaction

from .conftest import MOCK_PASSWORD, MOCK_TOKEN, MOCK_USERNAME

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TX1 = {
    "id": "TX1",
    "paidAt": "2026-01-15T10:30:00Z",
    "paymentName": "Season fee",
    "paidByName": "Alice Smith",
}
_TX2 = {
    "id": "TX2",
    "paidAt": "2026-02-01T08:00:00Z",
    "paymentName": "Kit",
    "paidByName": "Bob Jones",
}


class TestTransaction:
    """Unit tests for the `Transaction` typed model."""

    def test_transaction_parses_all_fields(self) -> None:
        t = Transaction.model_validate(_TX1)
        assert t.uid == "TX1"
        assert t.payment_name == "Season fee"
        assert t.paid_by_name == "Alice Smith"
        assert t.paid_at is not None

    def test_transaction_str(self) -> None:
        t = Transaction.model_validate(_TX1)
        s = str(t)
        assert "TX1" in s
        assert "Season fee" in s
        assert "Alice Smith" in s

    def test_transaction_minimal_only_id_required(self) -> None:
        """All non-uid fields have defaults; only `id` is required."""
        t = Transaction.model_validate({"id": "TX_MIN"})
        assert t.uid == "TX_MIN"
        assert t.payment_name == ""
        assert t.paid_by_name == ""
        assert t.paid_at is None

    def test_transaction_extra_fields_preserved(self) -> None:
        """Unknown Spond fields survive via `extra='allow'` and are accessible
        through the dict-compat shim."""
        import warnings as _w

        t = Transaction.model_validate({**_TX1, "futureField": "value"})
        assert "futureField" in t
        with _w.catch_warnings(record=True) as caught:
            _w.simplefilter("always")
            assert t["futureField"] == "value"
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)

    def test_transaction_dict_compat_subscript_warns(self) -> None:
        import warnings as _w

        t = Transaction.model_validate(_TX1)
        with _w.catch_warnings(record=True) as caught:
            _w.simplefilter("always")
            val = t["id"]
        assert val == "TX1"
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)


class TestSpondClubGetTransactions:
    """Integration tests for `SpondClub.get_transactions()` pagination."""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_transactions_single_page(self, mock_get) -> None:
        """A single page of results (< max_items) is returned without
        further recursive calls."""
        sc = SpondClub(MOCK_USERNAME, MOCK_PASSWORD)
        sc.token = MOCK_TOKEN

        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            side_effect=[[_TX1, _TX2], []]
        )

        txs = await sc.get_transactions(club_id="CLUB1", max_items=100)

        assert len(txs) == 2
        assert all(isinstance(t, Transaction) for t in txs)
        assert txs[0].uid == "TX1"
        assert txs[1].uid == "TX2"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_transactions_empty_result(self, mock_get) -> None:
        """If Spond returns an empty first page, an empty list comes back."""
        sc = SpondClub(MOCK_USERNAME, MOCK_PASSWORD)
        sc.token = MOCK_TOKEN

        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=[])

        txs = await sc.get_transactions(club_id="CLUB1")

        assert txs == []

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_transactions_paginates_until_empty(self, mock_get) -> None:
        """When the first page is full the method fetches additional pages
        until an empty page is returned."""
        sc = SpondClub(MOCK_USERNAME, MOCK_PASSWORD)
        sc.token = MOCK_TOKEN

        # Page 1: 2 items; page 2: 1 item; page 3: empty (stops)
        page3 = []
        page2 = [_TX2]
        page1 = [_TX1, _TX2]
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            side_effect=[page1, page2, page3]
        )

        txs = await sc.get_transactions(club_id="CLUB1", max_items=100)

        # 2 + 1 = 3 calls produced 2+1=3 Transaction objects
        assert len(txs) == 3

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_transactions_stops_at_max_items(self, mock_get) -> None:
        """Once `len(self.transactions) >= max_items`, no further page is
        fetched even if the last page was full."""
        sc = SpondClub(MOCK_USERNAME, MOCK_PASSWORD)
        sc.token = MOCK_TOKEN

        # Two-item page; max_items=2 means we must NOT recurse after page 1.
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=[_TX1, _TX2]
        )

        txs = await sc.get_transactions(club_id="CLUB1", max_items=2)

        assert len(txs) == 2
        # Only one HTTP call should have been made
        assert mock_get.call_count == 1

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_transactions_passes_club_id_header(self, mock_get) -> None:
        """The `X-Spond-Clubid` header must carry the supplied `club_id`."""
        sc = SpondClub(MOCK_USERNAME, MOCK_PASSWORD)
        sc.token = MOCK_TOKEN

        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=[])

        await sc.get_transactions(club_id="CLUB_ABC")

        _, kwargs = mock_get.call_args[0], mock_get.call_args[1]
        assert kwargs["headers"]["X-Spond-Clubid"] == "CLUB_ABC"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_transactions_skip_param_on_second_page(self, mock_get) -> None:
        """On the recursive call, `skip` must equal the number of records
        already fetched."""
        sc = SpondClub(MOCK_USERNAME, MOCK_PASSWORD)
        sc.token = MOCK_TOKEN

        # First page: 2 items; second page: empty
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            side_effect=[[_TX1, _TX2], []]
        )

        await sc.get_transactions(club_id="CLUB1", max_items=100)

        assert mock_get.call_count == 2
        second_call_params = mock_get.call_args_list[1][1].get("params")
        assert second_call_params == {"skip": 2}
