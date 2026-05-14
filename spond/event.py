"""Typed `Event` model with ActiveRecord-style behaviour.

`Event` instances are returned from `spond.spond.Spond.get_event()` and
`Spond.get_events()`. Each instance carries a reference back to the Spond
client (`_client`) so its methods can issue HTTP calls without the caller
having to thread the client through.

The class inherits from `DictCompatModel`, so existing dict-style consumers
(`event["heading"]`, `event["startTimestamp"]`, `event.get("id")`) keep
working with a `DeprecationWarning`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict, Field, PrivateAttr, ValidationError

from ._compat import DictCompatModel

if TYPE_CHECKING:
    from .spond import Spond


class EventType(StrEnum):
    """Known canonical values for `Event.type`.

    `Event.type` is typed as `str` rather than `EventType` because Spond may
    introduce new event kinds at any time — constraining the field to this
    enum would crash validation whenever an unknown value appears. Use these
    constants when comparing (`event.type == EventType.RECURRING`) but expect
    `event.type` itself to be a string.
    """

    EVENT = "EVENT"
    """A one-off event."""
    RECURRING = "RECURRING"
    """An occurrence of a recurring event."""
    AVAILABILITY = "AVAILABILITY"
    """An availability request (no fixed time)."""


class Responses(DictCompatModel):
    """The attendance-response lists attached to an `Event`.

    Each list holds raw member UIDs (`str`), not `Member` objects — resolving
    them to members requires a `Group` context which an Event doesn't carry
    standalone. To get `Member` objects, walk the parent group's `members`
    list and filter, or call `await event.accepted_members(spond)` (planned
    follow-up).
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    accepted_uids: list[str] = Field(default_factory=list, alias="acceptedIds")
    """UIDs of members who accepted the invitation."""
    declined_uids: list[str] = Field(default_factory=list, alias="declinedIds")
    """UIDs of members who declined."""
    unanswered_uids: list[str] = Field(default_factory=list, alias="unansweredIds")
    """UIDs of members who have not yet responded."""
    waiting_list_uids: list[str] = Field(default_factory=list, alias="waitinglistIds")
    """UIDs of members on the waiting list (event is full)."""
    unconfirmed_uids: list[str] = Field(default_factory=list, alias="unconfirmedIds")
    """UIDs of members whose response needs confirmation."""
    decline_messages: dict[str, dict[str, Any]] = Field(
        default_factory=dict, alias="declineMessages"
    )
    """Per-member decline-reason map. Keys are member UIDs (subset of
    `declined_uids`); each value is a `{profileId, message}` dict
    describing who entered the message and what they said."""


# Python field names that `Event.update()` strips from the POST payload.
# The set mirrors the pre-OO `_EVENT_TEMPLATE`'s implicit policy: only
# the curated set of writable fields the template included goes back on
# update. Anything else is read-only, server-managed, derived, or has its
# own dedicated endpoint — sending those back risks Spond treating stale
# local state as authoritative (the most concerning case being
# `responses`, which would clobber concurrent attendance changes).
_EVENT_READ_ONLY_FIELDS = frozenset(
    {
        # Server-managed identifiers / timestamps
        "creator_uid",
        "created_time",
        "updated",
        # Derived / boolean state flags
        "expired",
        "registered",
        "hidden",
        "cancelled",
        "match_event",
        "modified_from_series",
        # Series wiring (set when the event is part of a recurrence)
        "series_uid",
        "series_ordinal",
        # Nested objects with their own update paths
        "responses",
        "recipients",
        "comments",
        # Behalf-of list: not in the pre-OO writable template
        "behalf_of_uids",
    }
)


class Event(DictCompatModel):
    """A Spond event with attached operations.

    Construct via `Spond.get_event(uid)` or as elements of
    `Spond.get_events()` — both wire `_client` for you. Don't instantiate
    directly unless you also set `_client` (the ActiveRecord methods need
    it for HTTP).

    Example
    -------
    ```python
    event = await spond.get_event(uid)
    print(event.heading, event.start_time)
    for member_uid in event.responses.accepted_uids:
        print(member_uid)

    await event.update(description="Updated description")
    await event.change_response(member_uid, accepted=True)
    xlsx = await event.attendance_xlsx()
    ```
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        arbitrary_types_allowed=True,
    )

    # Core fields. Only `uid` is truly required for the SDK to be useful
    # at all (every method addresses an event by id); the others have
    # defaults so the SDK doesn't hard-fail if Spond ever drops a field
    # from its response shape. Defaults are deliberately sentinel-ish so
    # callers can distinguish "field absent" from "field genuinely empty".
    uid: str = Field(alias="id")
    heading: str = ""
    start_time: datetime | None = Field(default=None, alias="startTimestamp")
    end_time: datetime | None = Field(default=None, alias="endTimestamp")
    created_time: datetime | None = Field(default=None, alias="createdTime")
    type: str = ""
    """Spond's event-kind string. Common values are listed on `EventType`,
    but unknown values pass through unchanged so the SDK doesn't crash if
    Spond adds new variants."""
    responses: Responses = Field(default_factory=Responses)

    # Owner / creator metadata
    creator_uid: str | None = Field(default=None, alias="creatorId")
    owners: list[dict[str, Any]] = Field(default_factory=list)
    """Raw owner objects (typed `Owner` class is a possible future refinement)."""

    # Commonly present but treated as optional
    description: str | None = None
    visibility: str = "INVITEES"
    expired: bool = False
    hidden: bool = False
    cancelled: bool = False
    auto_accept: bool = Field(default=False, alias="autoAccept")
    auto_reminder_type: str = Field(default="DISABLED", alias="autoReminderType")
    participants_hidden: bool = Field(default=False, alias="participantsHidden")
    registered: bool = False
    comments_disabled: bool = Field(default=False, alias="commentsDisabled")
    match_event: bool = Field(default=False, alias="matchEvent")
    modified_from_series: bool = Field(default=False, alias="modifiedFromSeries")

    # Series fields (only for recurring events)
    series_uid: str | None = Field(default=None, alias="seriesId")
    series_ordinal: int | None = Field(default=None, alias="seriesOrdinal")

    # Update timestamp (Spond uses milliseconds since epoch here)
    updated: int | None = None

    # Behalf-of (members someone else can respond for)
    behalf_of_uids: list[str] = Field(default_factory=list, alias="behalfOfIds")

    # Nested data we keep as raw dicts for now (modelling these is follow-up work)
    location: dict[str, Any] | None = None
    """Location dict with `address`, `latitude`, `longitude`, etc. Unmodelled for now."""
    recipients: dict[str, Any] | None = None
    """Recipients dict with `group`, `profiles`, `guardians`. Unmodelled for now."""
    tasks: dict[str, Any] | None = None
    """Tasks dict with `openTasks`, `assignedTasks`. Unmodelled for now."""
    attachments: list[Any] = Field(default_factory=list)
    """Attachment objects. Unmodelled for now."""
    comments: list[Any] = Field(default_factory=list)
    """Comment objects. Only populated when fetched with `?includeComments=true`."""

    # Non-serialised reference back to the Spond client for HTTP calls.
    _client: Any = PrivateAttr(default=None)

    def __str__(self) -> str:
        start = self.start_time.isoformat() if self.start_time else "?"
        return f"Event(uid={self.uid!r}, heading={self.heading!r}, start_time={start})"

    @property
    def url(self) -> str:
        """Web URL of the event (for opening in a browser)."""
        return f"https://spond.com/client/sponds/{self.uid}/"

    @classmethod
    def from_api(cls, data: dict[str, Any], client: Spond | None) -> Event:
        """Construct an `Event` from a raw API response and bind the client.

        Used internally by `Spond.get_event()` and `Spond.get_events()`.
        Sets `_client` on the instance so the ActiveRecord methods can
        issue HTTP calls. `client` is `Optional` only so test fixtures
        can build typed instances without a live Spond — production
        callers always pass a real client, and any ActiveRecord method
        called on a `_client is None` instance raises `RuntimeError`
        (or `AttributeError` in the dereference path).
        """
        instance = cls.model_validate(data)
        instance._client = client
        return instance

    async def update(
        self, _updates: dict[str, Any] | None = None, /, **fields: Any
    ) -> Event:
        """POST changes to this event back to Spond and return the updated event.

        Accepts either Python-style attribute names (`description="..."`) or
        API-style aliases (`startTimestamp="..."`) — resolution is bounded
        to `Event.model_fields`, so keys that don't match a declared field
        in either form pass through to Spond verbatim under their original
        name. Spond is the ultimate arbiter of what the event API accepts,
        not this SDK.

        The POST payload is built from this Event's current state via
        `model_dump(by_alias=True, mode="json")`, then overlaid with the
        caller-supplied updates. `mode="json"` converts datetimes to ISO
        strings so aiohttp's `json.dumps` can serialise the payload.

        `_EVENT_READ_ONLY_FIELDS` (server-managed timestamps, derived flags,
        nested sub-resources like `responses` and `comments`) are stripped
        from the *dumped current state* only. Caller-supplied kwargs are
        **not** gated — a caller who explicitly passes `responses={...}` or
        `creatorId="X"` will see those keys reach Spond, and Spond decides
        whether to accept them. The filter exists to prevent the SDK from
        silently round-tripping stale local state, not to police explicit
        caller intent.

        Parameters
        ----------
        _updates : dict, positional-only, optional
            Dict of updates to apply. Useful when keys clash with Python
            reserved kwarg names like `self` or `cls` (which `**fields`
            can't carry), or when callers already have a dict in hand.
        **fields
            Field updates to send. Use the Python attribute name
            (`description`, `start_time`, …) or the API alias
            (`startTimestamp`, …) — either resolves correctly. Unknown keys
            pass through to the API verbatim. Merged on top of `_updates`
            if both are supplied.

        Returns
        -------
        Event
            A new `Event` reflecting the persisted state. The original
            instance is **not** mutated.
        """
        # Translate caller-supplied keys to API names. Unknown keys pass
        # through as-is so Spond-side changes don't get blocked client-side.
        combined: dict[str, Any] = {**(_updates or {}), **fields}
        api_updates: dict[str, Any] = {}
        for key, value in combined.items():
            py_name = self._resolve_dict_key(key)
            if py_name is None:
                api_updates[key] = value
            else:
                field_info = self.__class__.model_fields[py_name]
                api_updates[field_info.alias or py_name] = value

        # Dump the current state, then strip three classes of field:
        #   * read-only fields (creator, timestamps, server-managed flags,
        #     `responses`) — sending these back risks Spond treating stale
        #     local state as authoritative.
        #   * fields that weren't in the source API data (`exclude_unset`)
        #     — Pydantic tracks `model_fields_set` exactly so we know
        #     which fields came from Spond vs are class-level defaults.
        #     This is the critical guard: without it, defaulted empty
        #     collections (`owners=[]`, `attachments=[]`) and other
        #     sentinel-defaulted fields would round-trip back to Spond
        #     and could be interpreted as "clear this".
        #   * `None`-valued fields (`exclude_none`) — belt-and-suspenders
        #     for the same risk on dict-typed nested fields.
        # The caller's `api_updates` are overlaid afterwards, so explicit
        # updates always reach Spond regardless of source-data presence.
        payload = self.model_dump(
            by_alias=True,
            mode="json",
            exclude=_EVENT_READ_ONLY_FIELDS,
            exclude_unset=True,
            exclude_none=True,
        )
        payload.update(api_updates)

        url = f"{self._client.api_url}sponds/{self.uid}"
        async with self._client.clientsession.post(
            url, json=payload, headers=self._client.auth_headers
        ) as r:
            new_data = await r.json()

        # Spond usually returns the updated event on POST, but if the
        # response is partial (status-only, an error wrapper, etc.) the
        # construction below would crash with ValidationError. Fall back to
        # a fresh fetch in that case. **Order matters**: invalidate the
        # cache entry first so the fallback `get_events()` actually
        # re-fetches from the API rather than returning the stale `self`
        # that's still in the cache.
        #
        # `type(self)` (not literal `Event`) preserves subclass identity —
        # a `Match` updated via Event.update stays a `Match` so subsequent
        # `spond.get_event(uid)` doesn't silently demote to plain Event
        # (which would lose `match_info`).
        try:
            new_event = type(self).from_api(new_data, self._client)
        except ValidationError:
            # Drop the whole events cache so `get_event()` re-fetches via
            # `get_events()` instead of resolving from the stale cache.
            # That re-fetch routes through `_typed_event` and picks the
            # right subclass automatically.
            self._client.events = None
            new_event = await self._client.get_event(self.uid)

        # Keep the client's events cache coherent — replace the matching
        # entry in-place so subsequent `spond.get_event(uid)` calls don't
        # serve the stale pre-update instance. Index-based replacement
        # preserves the cache's list identity (callers holding a
        # reference to `spond.events` keep their list).
        if self._client.events is not None:
            for i, cached in enumerate(self._client.events):
                if cached.uid == self.uid:
                    self._client.events[i] = new_event
                    break

        return new_event

    async def change_response(
        self,
        member_uid: str,
        *,
        accepted: bool,
        decline_message: str | None = None,
    ) -> dict[str, Any]:
        """Set a member's response on this event.

        Parameters
        ----------
        member_uid : str
            UID of the member whose response to set. This is the **member's**
            id (`group["members"][i]["id"]`), not a profile id and not the
            authenticated user's id.
        accepted : bool
            True to accept, False to decline.
        decline_message : str, optional
            Reason for declining. When `accepted=False`, the message is
            forwarded to Spond if provided. When `accepted=True`, the
            message is **not** auto-cleared — any prior decline message
            stays on the response server-side unless you explicitly pass
            `decline_message=""` to clear it, or follow up with a separate
            edit through Spond's UI.

        Returns
        -------
        dict
            The event's `responses` object as returned by the API, with the
            updated id lists (`acceptedIds`, `declinedIds`, …).
        """
        payload: dict[str, Any] = {"accepted": str(accepted).lower()}
        if decline_message is not None:
            # Forward unconditionally if explicitly provided — lets callers
            # pass `decline_message=""` to clear a prior message when
            # flipping accepted=True.
            payload["declineMessage"] = decline_message

        url = f"{self._client.api_url}sponds/{self.uid}/responses/{member_uid}"
        async with self._client.clientsession.put(
            url, headers=self._client.auth_headers, json=payload
        ) as r:
            return await r.json()

    async def attendance_xlsx(self) -> bytes:
        """Download Spond's attendance-history XLSX for this event.

        Thin wrapper around Spond's web-UI "Export attendance history"
        feature — the columns and format are determined by Spond, not by
        this library, and notably the export does not include member ids.
        For a customisable CSV alternative, see `examples/attendance.py`.

        Returns
        -------
        bytes
            Raw XLSX bytes, typically written directly to disk:

            ```python
            import pathlib

            data = await event.attendance_xlsx()
            pathlib.Path(f"{event.uid}.xlsx").write_bytes(data)
            ```
        """
        url = f"{self._client.api_url}sponds/{self.uid}/export"
        async with self._client.clientsession.get(
            url, headers=self._client.auth_headers
        ) as r:
            return await r.read()
