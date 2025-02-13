import argparse
import asyncio
import csv
from pathlib import Path

from config import club_id, password, username

from spond.club import SpondClub

parser = argparse.ArgumentParser(
    description="Creates an transactions.csv to keep track of payments accessible on Spond Club"
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


async def main():
    output_path = Path("./exports/transactions.csv")

    s = SpondClub(username=username, password=password)
    transactions = await s.get_transactions(club_id=club_id, max_items=args.max)
    if not transactions:
        print("No transactions found.")
        await s.clientsession.close()
        return

    header = transactions[0].keys()

    with open(output_path, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=header)
        writer.writeheader()
        for t in transactions:
            writer.writerow(t)

    print(f"Collected {len(transactions)} transactions. Written to {output_path}")
    await s.clientsession.close()


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())
