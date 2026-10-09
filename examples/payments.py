import asyncio
import pandas as pd

from config import password, username
from spond import spond

# Get Payment Data 


async def main() -> None:
    s = spond.Spond(username=username, password=password)
    received_payments = await s.get_received_payments(100)

    df = pd.DataFrame(received_payments)
    df.to_excel("payment_data.xlsx", index=False)

    await s.clientsession.close() 

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())

