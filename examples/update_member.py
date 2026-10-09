import asyncio
import pprint

from config import password, username, group_id
from spond import spond

# Get Payment Data 

#
# This is an example of reading the Spond group data and extacting the ids
# for the custom subgroups, fields and roles
#
# Lots of globals as code is used in Jupyter notebook across different cells
#
async def get_spond_group(s) -> None:
    global members, fieldDefs, field_id_race_plate
    global field_id_date_added, field_id_grade, field_id_racing_category
    global field_id_leave_early, field_id_ride_home, field_id_school
    global subGroup_coaches_id, subGroup_hub_id, subGroup_alumni_id

    result = await s.get_group(group_id)

    members   = result['members']
    subGroups = result['subGroups']
    fieldDefs = result['fieldDefs']
    roles     = result['roles']
    
    for subGroup in subGroups:
        if subGroup['name'] == 'Marketplace':
            subGroup_hub_id = subGroup['id']
        elif subGroup['name'] == 'Coaches':
            subGroup_coaches_id = subGroup['id']
        elif subGroup['name'] == 'Alumni':
            subGroup_alumni_id = subGroup['id']
    
    for field in fieldDefs:
        if field['name'] == 'Date Added to Spond':
            field_id_date_added = field['id']
        elif field['name'] == 'Grade':
            field_id_grade = field['id']
        elif field['name'] == 'Racing Category':
            field_id_racing_category = field['id']
        elif field['name'] == 'School':
            field_id_school = field['id']
        elif field['name'] == 'Race Plate':
            field_id_race_plate = field['id']
        elif field['name'] == 'Allowed to leave early?':
            field_id_leave_early = field['id']
        elif field['name'] == 'Allowed to ride home?':
            field_id_ride_home = field['id']
    
    for role in roles:
        if role['name'] == 'Team Admin':
            rold_id_team_admin = role['id']  # noqa: F841
        elif role['name'] == 'Coach':
            rold_id_coach = role['id']   # noqa: F841


async def main() -> None:

    s = spond.Spond(username=username, password=password)

    if "members" not in globals():
        await get_spond_group(s)

    # gets the last member with first name Test
    m=None
    for member in members:
        if member['firstName'] == 'Test':
            m = member

    # Change the racing category for member with first name Test to 1
    if (m is not None):
        # change value in a custom field
        member_fields = m['fields']
        member_fields[field_id_racing_category] = "1"

        # Write the member data back to Spond
        response = await s.update_member(group_id, m)

	# Give some feedback!
        print ("updated " + m['firstName'] + ' ' + m['lastName'])
        pprint.pprint (response)
    else:
        print("Could not find a member with first name Test")

    await s.clientsession.close() 

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())



