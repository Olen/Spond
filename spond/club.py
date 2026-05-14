"""Client for the Spond Club finance API.

Spond Club is the paid administration tier sold to clubs/teams alongside the
free consumer app. It exposes a separate API (`api.spond.com/club/v1/`) for
finance-flavoured data such as transactions/payments. Use the `SpondClub`
class for this API and `spond.spond.Spond` for everything else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from .base import _SpondBase

if TYPE_CHECKING:
    from . import JSONDict


class SpondClub(_SpondBase):
    """Async client for the Spond Club finance API.

    Authentication is shared with the consumer API — the same email/password
    credentials work, but the user must belong to at least one Spond Club
    organisation and the `club_id` passed to each method must be one they
    have access to. The `club_id` here is distinct from the consumer-API
    `groupId`.

    Example
    -------
    ```python
    import asyncio
    from spond import club

    async def main():
        sc = club.SpondClub(username="me@example.invalid", password="secret")
        txs = await sc.get_transactions(club_id="ABCD1234...", max_items=50)
        for t in txs:
            print(t["paidAt"], t["paymentName"], t["paidByName"])
        await sc.clientsession.close()

    asyncio.run(main())
    ```
    """

    _API_BASE_URL: ClassVar = "https://api.spond.com/club/v1/"

    def __init__(self, username: str, password: str) -> None:
        """Construct a Spond Club client.

        Parameters
        ----------
        username : str
            Spond account email. Same credentials as the consumer API; the
            account must have access to at least one Spond Club organisation
            for the API calls to return data.
        password : str
            Spond account password.
        """
        super().__init__(username, password, self._API_BASE_URL)
        self.transactions: list[JSONDict] | None = None

    @_SpondBase.require_authentication
    async def get_transactions(
        self, club_id: str, skip: int | None = None, max_items: int = 100
    ) -> list[JSONDict]:
        """Retrieve transactions/payments for a Spond Club.

        Spond's transactions endpoint returns at most 25 records per request,
        so this method paginates internally (via recursion on `skip`) until
        either `max_items` is reached or the server returns an empty page.

        **Caching caveat**: results accumulate on `self.transactions` and
        the cache is **not** keyed by `club_id` — calling this method again
        with a different `club_id` on the same instance will append that
        club's transactions to the same list, mixing the two. If you query
        multiple clubs from one client, reset the cache between calls
        (`sc.transactions = None`) or use a fresh `SpondClub` instance per
        club.

        Each transaction dict typically includes at least `id`, `paidAt`,
        `paymentName`, and `paidByName`. See `examples/transactions.py` for
        a usage example.

        Parameters
        ----------
        club_id : str
            Identifier for the club. Note that this is **different** from the
            `groupId` used elsewhere in the Spond API — find it in the URL
            of the Spond Club web UI.
        skip : int, optional
            Pagination cursor (number of records to skip). Normally left as
            `None`; the method increments it itself on recursive calls. Only
            override if you know what you're doing.
        max_items : int, optional
            Stop fetching once at least this many transactions are
            accumulated. Defaults to 100. The final list may be slightly
            longer than `max_items` since the server returns pages of 25.

        Returns
        -------
        list[JSONDict]
            All transactions accumulated so far (across recursive page
            fetches). Empty list if the club has no transactions.
        """
        if self.transactions is None:
            self.transactions = []

        url = f"{self.api_url}transactions"
        params = None if skip is None else {"skip": skip}
        headers = {**self.auth_headers, "X-Spond-Clubid": club_id}

        async with self.clientsession.get(url, headers=headers, params=params) as r:
            if r.status == 200:
                t = await r.json()
                if len(t) == 0:
                    return self.transactions

                self.transactions.extend(t)
                if len(self.transactions) < max_items:
                    return await self.get_transactions(
                        club_id=club_id,
                        skip=len(t) if skip is None else skip + len(t),
                        max_items=max_items,
                    )

        return self.transactions
