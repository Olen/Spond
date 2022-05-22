from datetime import date
import os
import argparse
import asyncio
import csv
from spond import spond
from config import username, password

parser = argparse.ArgumentParser(description="Creates an attendance.csv for organizers of events.")
parser.add_argument("-f", "--from", help="First date to query for. Date is included in results (format YYYY-MM-DD)", type=date.fromisoformat, dest="f")
parser.add_argument("-t", "--to", help="Last date to query for. Date is excluded from results (format YYYY-MM-DD)", type=date.fromisoformat, dest="t")
parser.add_argument("-a", help="Also include all members", default=False, action='store_true')
args = parser.parse_args()

async def main():
    s = spond.Spond(username=username, password=password)
    events = await s.getEventsBetween(args.f, args.t)
    
    if not os.path.exists('./exports'):
            os.makedirs('./exports')

    for e in events:
        filename = os.path.join("./exports", f"{e['startTimestamp']}-{e['heading']}.csv")
        with open(filename, 'w', newline='') as csvfile:
            spamwriter = csv.writer(csvfile, delimiter=',',
                            quotechar='"', quoting=csv.QUOTE_MINIMAL)
        
            spamwriter.writerow(["Start","End","Description","Name","Answer","Organizer"])
            for o in e['owners']:
                person = await s.getPerson(o['id'])
                fullName = person['firstName'] + ' ' + person['lastName']
                spamwriter.writerow([e['startTimestamp'], e['endTimestamp'], e['heading'], fullName, o['response'], "X"])
            if args.a is True:
                for r in e['responses']['acceptedIds']:
                    person = await s.getPerson(r)
                    fullName = person['firstName'] + ' ' + person['lastName']
                    spamwriter.writerow([e['startTimestamp'], e['endTimestamp'], e['heading'], fullName, 'accepted'])
                for r in e['responses']['declinedIds']:
                    person = await s.getPerson(r)
                    fullName = person['firstName'] + ' ' + person['lastName']
                    spamwriter.writerow([e['startTimestamp'], e['endTimestamp'], e['heading'], fullName, 'declined'])
                for r in e['responses']['unansweredIds']:
                    person = await s.getPerson(r)
                    fullName = person['firstName'] + ' ' + person['lastName']
                    spamwriter.writerow([e['startTimestamp'], e['endTimestamp'], e['heading'], fullName, 'unanswered'])
                for r in e['responses']['unconfirmedIds']:
                    person = await s.getPerson(r)
                    fullName = person['firstName'] + ' ' + person['lastName']
                    spamwriter.writerow([e['startTimestamp'], e['endTimestamp'], e['heading'], fullName, 'unconfirmed'])
                for r in e['responses']['waitinglistIds']:
                    person = await s.getPerson(r)
                    fullName = person['firstName'] + ' ' + person['lastName']
                    spamwriter.writerow([e['startTimestamp'], e['endTimestamp'], e['heading'], fullName, 'waitinglist'])
                    
            
    await s.clientsession.close()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())

