"""Module containing `Event` class and related `EventType`,`Responses` classes."""

import sys

if sys.version_info < (3, 11):
    from typing_extensions import Self
else:
    from typing import Self


from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .types import DictFromJSON


class Responses(BaseModel):
    """Represents the responses to an `Event`."""

    # Lists which always exist in API data, but may be empty
    accepted_uids: list[str] = Field(alias="acceptedIds")
    """`acceptedIds` in Spond API.
    May be empty."""
    declined_uids: list[str] = Field(alias="declinedIds")
    """`declinedIds` in Spond API.
    May be empty."""
    unanswered_uids: list[str] = Field(alias="unansweredIds")
    """`unansweredIds` in Spond API.
    May be empty."""
    waiting_list_uids: list[str] = Field(alias="waitinglistIds")
    """`waitinglistIds` in Spond API.
    May be empty."""
    unconfirmed_uids: list[str] = Field(alias="unconfirmedIds")
    """`unconfirmedIds` in Spond API.
    May be empty."""


class EventType(Enum):
    """Represents the kind of `Event`."""

    AVAILABILITY = "AVAILABILITY"
    """Availability request."""
    EVENT = "EVENT"
    RECURRING = "RECURRING"


class Event(BaseModel):
    """Represents an event in the Spond system."""

    uid: str = Field(alias="id")
    """`id` in Spond API; aliased as that's a Python built-in, and the Spond package
    uses `uid`."""
    heading: str
    responses: Responses
    type: EventType
    created_time: datetime = Field(alias="createdTime")
    """Derived from `createdTime` in Spond API."""
    end_time: datetime = Field(alias="endTimestamp")
    """Datetime at which the `Event` ends.
    Derived from `endTimestamp` in Spond API."""
    start_time: datetime = Field(alias="startTimestamp")
    """Datetime at which the `Event` starts.
    Derived from `startTimestamp` in Spond API."""

    # Optional in API data
    cancelled: bool | None = Field(default=None)
    """Not always present."""
    invite_time: datetime | None = Field(alias="inviteTime", default=None)
    """Derived from `inviteTime` in Spond API.
    Not always present."""

    def __str__(self) -> str:
        """Return simple human-readable description.

        Includes only key fields in custom order.
        """
        return (
            f"Event(uid='{self.uid}', "
            f"heading='{self.heading}', "
            f"start_time: {self.start_time}, "
            "…)"
        )

    @property
    def url(self) -> str:
        """Return the URL of the `Event`, for convenience."""
        return f"https://spond.com/client/sponds/{self.uid}/"

    @classmethod
    def from_dict(cls, dict_: DictFromJSON) -> Self:
        """Construct an `Event`.

        Parameters
        ----------
        dict_
            as returned by `spond.spond.Spond.get_event()`
            or from the list returned by `spond.spond.Spond.get_events()`.

        Returns
        -------
        `Event`
        """
        return cls(**dict_)
