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

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict, Field, PrivateAttr, ValidationError
from pydantic_core import to_jsonable_python

from ._compat import DictCompatModel
from .exceptions import SpondAPIError

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

    def _natural_key(self) -> tuple | None:
        """Entity-identity tuple. uid-based when set; otherwise the
        `(heading, start_time)` pair lets a freshly-constructed event
        compare equal to itself across copies (useful when staging an
        event before `Spond.create_event()` is called).
        """
        if self.uid:
            return ("Event", self.uid)
        if self.heading or self.start_time:
            return ("Event", None, self.heading, self.start_time)
        return None

    @property
    def url(self) -> str:
        """Web URL of the event (for opening in a browser)."""
        return f"https://spond.com/client/sponds/{self.uid}/"

    @property
    def is_past(self) -> bool:
        """True when the event has finished (or started, if no `end_time`).

        An event with no `start_time` is never "past" (the API hasn't
        committed it to a calendar slot yet) — returns False.
        """
        # Prefer end_time; fall back to start_time when end isn't set.
        reference = self.end_time or self.start_time
        if reference is None:
            return False
        return reference < datetime.now(UTC)

    @property
    def is_upcoming(self) -> bool:
        """True when the event hasn't started yet. Opposite face of
        `is_past`, but **not** strictly its negation — an event with no
        `start_time` returns False for both."""
        if self.start_time is None:
            return False
        return self.start_time > datetime.now(UTC)

    @property
    def duration(self) -> timedelta | None:
        """`end_time - start_time` when both are present; otherwise `None`.

        Returns a `datetime.timedelta`. Useful for calendar sync, slot
        comparison, and reporting.
        """
        if self.start_time is None or self.end_time is None:
            return None
        return self.end_time - self.start_time

    def response_for(self, member_uid: str) -> str | None:
        """Return the response status of `member_uid` on this event.

        Returns one of `"accepted"`, `"declined"`, `"unanswered"`,
        `"waiting_list"`, `"unconfirmed"` — or `None` if the uid doesn't
        appear in any of the response lists (i.e. not invited).

        Synchronous; reads from the already-populated `responses` field.
        Doesn't issue HTTP. Pair with `await event.accepted_members()`
        and siblings to resolve uids → typed members.
        """
        if not self.responses:
            return None
        for status, uids in (
            ("accepted", self.responses.accepted_uids),
            ("declined", self.responses.declined_uids),
            ("unanswered", self.responses.unanswered_uids),
            ("waiting_list", self.responses.waiting_list_uids),
            ("unconfirmed", self.responses.unconfirmed_uids),
        ):
            if member_uid in uids:
                return status
        return None

    def has_responded(self, member_uid: str) -> bool:
        """True when `member_uid` has given any concrete response
        (`accepted`, `declined`, `waiting_list`, or `unconfirmed`) — i.e.
        their uid is in any list other than `unanswered_uids`."""
        status = self.response_for(member_uid)
        return status is not None and status != "unanswered"

    async def _resolve_uids_to_persons(self, uids: list[str]) -> list[Any]:
        """Resolve member UIDs to typed `Member`/`Guardian` objects.

        Walks the client's `groups` cache (fetching via `get_groups()` if
        empty) and returns one typed `Person` per uid. UIDs that don't
        match any current group member are silently skipped — Spond
        sometimes retains response records for members who've since left.

        Used by `accepted_members()` and siblings. Requires `_client`.
        """
        if self._client is None:
            raise RuntimeError(
                "Event has no client attached; member-resolution helpers "
                "require an instance constructed via Spond.get_event() or "
                "Spond.get_events()."
            )
        if not self._client.groups:
            await self._client.get_groups()
        if not self._client.groups:
            return []
        # Build a single uid → person lookup across all groups, so the
        # per-uid scan is O(uids) not O(uids × groups × members).
        index: dict[str, Any] = {}
        for group in self._client.groups:
            for member in group.members:
                index.setdefault(member.uid, member)
                for guardian in member.guardians:
                    index.setdefault(guardian.uid, guardian)
        return [index[uid] for uid in uids if uid in index]

    async def accepted_members(self) -> list[Any]:
        """Resolve `responses.accepted_uids` to typed `Member`/`Guardian`
        objects via the client's group cache. Lazy — fetches groups if the
        cache is empty.

        Returns
        -------
        list[Member | Guardian]
            One typed `Person` per uid that still resolves to a current
            group member. UIDs that no longer correspond to a member of
            any group are silently omitted from the result.

        Raises
        ------
        RuntimeError
            The Event was constructed without a client (e.g. via
            `Event.model_validate(raw)` directly rather than
            `Spond.get_event()`). Helpers need a client to fetch groups.
        """
        return await self._resolve_uids_to_persons(self.responses.accepted_uids)

    async def declined_members(self) -> list[Any]:
        """Resolve `responses.declined_uids` to typed `Member`/`Guardian`
        objects. See `accepted_members` for semantics."""
        return await self._resolve_uids_to_persons(self.responses.declined_uids)

    async def unanswered_members(self) -> list[Any]:
        """Resolve `responses.unanswered_uids` to typed `Member`/`Guardian`
        objects. See `accepted_members` for semantics."""
        return await self._resolve_uids_to_persons(self.responses.unanswered_uids)

    async def waiting_list_members(self) -> list[Any]:
        """Resolve `responses.waiting_list_uids` to typed `Member`/`Guardian`
        objects. See `accepted_members` for semantics."""
        return await self._resolve_uids_to_persons(self.responses.waiting_list_uids)

    async def unconfirmed_members(self) -> list[Any]:
        """Resolve `responses.unconfirmed_uids` to typed `Member`/`Guardian`
        objects. See `accepted_members` for semantics."""
        return await self._resolve_uids_to_persons(self.responses.unconfirmed_uids)

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
        # `model_dump(mode="json")` converts native Python types (datetime,
        # UUID, Decimal, sets, …) to JSON-safe equivalents, but the
        # caller's `api_updates` haven't been through that pass. Run them
        # through the same encoder so callers can pass typed values
        # naturally — `event.update(start_time=datetime.now())` is the
        # obvious shape, given the field is itself a `datetime`.
        payload.update({k: to_jsonable_python(v) for k, v in api_updates.items()})

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

    async def save(self, client: Spond | None = None) -> Event:
        """Persist this event to Spond — universal create-or-update.

        - When `self.uid` is empty (a freshly-constructed instance):
          POSTs to `/sponds/` to create. Spond returns the new event
          with `uid` populated; the result is **applied to self in
          place** so the same instance can be used for subsequent
          calls.
        - When `self.uid` is set: POSTs to `/sponds/{uid}` (the same
          path `update()` uses) to persist whatever local state the
          caller has mutated.

        On first save of an unbound instance, pass `client=spond` to
        bind a Spond client. Subsequent saves use the bound client.

        Example
        -------
        ```python
        # Create
        event = Event(heading="Match vs Rivals",
                      start_time=..., end_time=...,
                      recipients={"group": {"id": "GROUPUID"}},
                      owners=[{"id": my_profile_uid, "response": "accepted"}])
        await event.save(client=spond)
        assert event.uid  # populated by Spond

        # Mutate + save
        event.heading = "Renamed"
        await event.save()
        ```

        Returns `self` (mutated in place) for chaining. Compare with
        `update(**fields)` which returns a *new* instance — both shapes
        are supported; pick whichever matches your code style.

        Raises
        ------
        RuntimeError
            No client is bound and `client` was not supplied.
        SpondAPIError
            Spond rejected the create or update.
        """
        if client is not None:
            self._client = client
        if self._client is None:
            raise RuntimeError(
                "Event has no client bound. Pass `client=spond` to "
                "`event.save(client=...)` on first save."
            )

        if self.uid:
            # Update path — round-trip through `update()` so all the
            # payload-discipline machinery (exclude_unset, read-only
            # filter, JSON-encoding of caller values) applies. Then
            # mutate self with the refreshed state.
            refreshed = await self.update()
        else:
            # Create path — POST to /sponds/ (collection endpoint).
            # We do NOT apply `_EVENT_READ_ONLY_FIELDS` here: that
            # filter exists to prevent stale-state round-tripping on
            # update, but on create the caller's explicit state is
            # all we have to work with — `recipients` in particular
            # is required by Spond's create endpoint.
            # Server-managed fields (creator_uid, created_time,
            # updated, expired, registered, …) are still excluded
            # because they default to None and exclude_none=True
            # drops them, OR they're in model_fields_set as None and
            # exclude_none=True drops them.
            payload = self.model_dump(
                by_alias=True,
                mode="json",
                exclude_unset=True,
                exclude_none=True,
            )
            # Drop the empty `id` if it slipped through — Spond mints
            # a fresh uid on create.
            payload.pop("id", None)
            url = f"{self._client.api_url}sponds/"
            async with self._client.clientsession.post(
                url, json=payload, headers=self._client.auth_headers
            ) as r:
                if not r.ok:
                    raise SpondAPIError(r.status, await r.text(), url)
                new_data = await r.json()
            refreshed = type(self).from_api(new_data, self._client)
            # Append to the client cache so subsequent `get_event(uid)`
            # resolves the new event without a re-fetch.
            if self._client.events is None:
                self._client.events = [refreshed]
            else:
                self._client.events.insert(0, refreshed)

        # Apply the refreshed state to self IN PLACE — this is the
        # ActiveRecord contract: after `save()`, `self` is the
        # authoritative live record.
        for field_name in type(self).model_fields:
            object.__setattr__(self, field_name, getattr(refreshed, field_name))
        # Capture any extras Spond added that we don't model.
        extras = refreshed._pydantic_extras()
        if extras and self.__pydantic_extra__ is not None:
            self.__pydantic_extra__.update(extras)
        # Sync `model_fields_set` so subsequent `exclude_unset=True`
        # dumps reflect what Spond actually emitted (not our pre-save
        # snapshot).
        self.__pydantic_fields_set__ = set(refreshed.__pydantic_fields_set__)
        return self

    async def delete(self) -> None:
        """Delete this event from Spond.

        Issues `DELETE /sponds/{uid}` and removes the event from the
        client's `events` cache. After this call, `self.uid` is left
        in place (so callers can still reference what was deleted),
        but any subsequent `save()` would attempt to update a no-longer-
        existing event and fail.

        Raises
        ------
        RuntimeError
            The event has no client bound or no `uid` (i.e. it was
            never persisted to begin with).
        SpondAPIError
            Spond rejected the delete.
        """
        if self._client is None:
            raise RuntimeError("Event has no client bound; cannot delete.")
        if not self.uid:
            raise RuntimeError(
                "Cannot delete an unsaved Event (no uid). Call save() first "
                "or construct the instance via Spond.get_event()."
            )
        url = f"{self._client.api_url}sponds/{self.uid}"
        async with self._client.clientsession.delete(
            url, headers=self._client.auth_headers
        ) as r:
            if not r.ok:
                raise SpondAPIError(r.status, await r.text(), url)
        # Remove from cache so subsequent get_event(uid) raises rather
        # than serving a stale entry.
        if self._client.events is not None:
            self._client.events = [e for e in self._client.events if e.uid != self.uid]
