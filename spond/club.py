from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from .base import _SpondBase

if TYPE_CHECKING:
    from . import JSONDict


class SpondClub(_SpondBase):
    _API_BASE_URL: ClassVar = "https://api.spond.com/club/v1/"

    def __init__(self, username: str, password: str) -> None:
        super().__init__(username, password, self._API_BASE_URL)
        self.transactions: list[JSONDict] | None = None

    @_SpondBase.require_authentication
    async def get_transactions(
        self, club_id: str, skip: int | None = None, max_items: int = 100
    ) -> list[JSONDict]:
        """
        Retrieves a list of transactions/payments for a specified club.

        Parameters
        ----------
        club_id : str
            Identifier for the club. Note that this is different from the Group ID used
            in the core API.
        max_items : int, optional
            The maximum number of transactions to retrieve. Defaults to 100.
        skip : int, optional
            This endpoint only returns 25 transactions at a time (page scrolling).
            Therefore, we need to increment this `skip` param to grab the next
            25 etc. Defaults to None. It's better to keep `skip` at None
            and specify `max_items` instead. This param is only here for the
            recursion implementation

        Returns
        -------
        list[JSONDict]
            A list of transactions, each represented as a dictionary.
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
