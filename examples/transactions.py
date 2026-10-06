"""Spond Club transactions CSV export.

Uses the v2.x typed `Transaction` instances; `model_dump(by_alias=True)`
gives the same row shape the pre-OO dict export produced.
"""

import argparse
import asyncio
import csv
from pathlib import Path

from config import club_id, password, username

from spond.club import SpondClub

EXPORT_DIRPATH = Path("./exports")

parser = argparse.ArgumentParser(
    description=(
        "Creates a transactions.csv to keep track of payments accessible on Spond Club"
    )
)
parser.add_argument(
    "-m",
    "--max",
    help="The max number of transactions to query for",
    type=int,
    dest="max",
    default=1000,
)
args = parser.parse_args()


async def main() -> None:
    async with SpondClub(username=username, password=password) as s:
        transactions = await s.get_transactions(club_id=club_id, max_items=args.max)

    if not transactions:
        print("No transactions found.")
        return

    EXPORT_DIRPATH.mkdir(exist_ok=True)
    csv_filepath = EXPORT_DIRPATH / "transactions.csv"

    # Each Transaction is a Pydantic model — dump with `by_alias=True`
    # to get camelCase column names matching Spond's wire shape (the
    # same shape the pre-OO dict export used). `model_dump(mode="json")`
    # converts datetime fields to ISO strings so csv.DictWriter can
    # write them without further conversion.
    rows = [
        t.model_dump(by_alias=True, mode="json", exclude_none=True)
        for t in transactions
    ]
    header = sorted({k for row in rows for k in row})

    with csv_filepath.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Collected {len(transactions)} transactions. Written to {csv_filepath}")


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())
