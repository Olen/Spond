"""Module contains template event data, to be used as a base when updating events."""

from spond import JSONDict

_EVENT_TEMPLATE: JSONDict = {
    "heading": None,
    "description": None,
    "spondType": "EVENT",
    "startTimestamp": None,
    "endTimestamp": None,
    "commentsDisabled": False,
    "maxAccepted": 0,
    "rsvpDate": None,
    "location": {
        "id": None,
        "feature": None,
        "address": None,
        "latitude": None,
        "longitude": None,
    },
    "owners": [{"id": None}],
    "visibility": "INVITEES",
    "participantsHidden": False,
    "autoReminderType": "DISABLED",
    "autoAccept": False,
    "payment": {},
    "attachments": [],
    "id": None,
    "tasks": {
        "openTasks": [],
        "assignedTasks": [
            {
                "name": None,
                "description": "",
                "type": "ASSIGNED",
                "id": None,
                "adultsOnly": True,
                "assignments": {"memberIds": [], "profiles": [], "remove": []},
            }
        ],
    },
}
