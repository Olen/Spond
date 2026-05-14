# Spond OO rewrite — design

**Status:** open for feedback — work in progress on branch `feat/oo-rewrite`
**Last updated:** 2026-05-14
**Scope:** First-class typed objects with ActiveRecord behaviour, replacing the dict-based return surface across `spond.spond.Spond` and `spond.club.SpondClub`.

## Feedback welcome

This document is the design we're proposing for the long-discussed object-oriented rewrite of the SDK. It's the spec — not the code yet. Comments, pushback, and suggestions on any section are welcome before the implementation lands.

- **For high-level concerns** (API shape, scope, deprecation path) — open an issue titled `OO rewrite: …` or comment on the tracking PR.
- **For specific wording or examples** — review the draft PR (link will be added here once it's open) and comment inline.
- **For deeper design questions** — see the "Open questions" section near the end; we'd like to settle those before the implementation locks them in.

Decisions captured here have been agreed in principle but are still revisable as long as v1.3 hasn't shipped.

## Motivation

The current SDK exposes one big `Spond` class with ~13 methods, all of them taking and returning `dict[str, Any]` (`JSONDict`). Callers must navigate raw dicts (`event["responses"]["acceptedIds"][0]`), there's no validation of API responses, and operations on a single event are scattered across `update_event(uid, ...)`, `change_response(uid, user, ...)`, `get_event_attendance_xlsx(uid)`.

The OO rewrite addresses three things at once:

1. **Self-contained objects.** Operations on an event live on the event: `event.update(...)`, `event.change_response(...)`, `event.attendance_xlsx()`.
2. **Typed navigation.** `group.members[i].guardians[j].first_name` works with autocomplete and type-checker support.
3. **Validation on construction.** Pydantic raises loudly if Spond's API drifts, instead of silently passing through unexpected shapes.

## Decisions locked during brainstorming

| Decision | Choice | Why |
|---|---|---|
| OO shape | **ActiveRecord** (instance owns operations) | Closest to "self-contained, well-behaved"; smaller refactor than Manager pattern; keeps `Spond.get_event(uid)` etc. on the client |
| Migration | **Side-by-side with deprecation** | Old method-on-Spond surface stays, emits `DeprecationWarning`, gets removed in a future major bump |
| Data-class tech | **Pydantic v2** | Runtime validation + clean snake_case ↔ camelCase aliasing; elliot-100's stale `oo-rewrite` branch already proved this works; ~5MB dep is fine alongside aiohttp |
| Pilot scope | **All types at once** | Half-OO state leaves inter-dependency gaps (e.g., `Group.members` returning Member objects requires Member to also be typed) |
| PR cadence | **Single draft PR** | One coherent change; most of the diff is new files |
| Person hierarchy | **Person base, Member/Guardian derived** | Members and Guardians have different behaviour: members are invited and respond to events; guardians manage a child member and may respond on their behalf |

## Type inventory

```
Person (base, BaseModel + DictCompatMixin)
  ├─ uid, first_name, last_name, email (optional), profile (optional)
  ├─ full_name (property)
  │
  ├─ Member(Person)
  │    ├─ guardians: list[Guardian]
  │    ├─ (subgroup memberships, roles — TBD during impl based on actual API shape)
  │    └─ methods: send_message(text, group_uid)
  │
  └─ Guardian(Person)
       ├─ (link to managed member if API exposes it)
       └─ methods: send_message(text, group_uid) — routes to guardian

Event(BaseModel + DictCompatMixin)
  ├─ uid, heading, start_time, end_time, type: EventType, owners, recipients, ...
  ├─ responses: Responses
  ├─ methods: update(**fields), change_response(member_uid, *, accepted, decline_message=None),
  │           attendance_xlsx() -> bytes
  │
  └─ Match(Event)  — sports fixtures
       ├─ match_info: MatchInfo | None  — team/opponent names, scores, HOME/AWAY
       └─ Spond.get_events() / get_event() return Match (not plain Event)
          when the API record has matchEvent=True.

Responses (sub-object of Event)
  ├─ accepted_uids, declined_uids, unanswered_uids, waiting_list_uids, unconfirmed_uids
  │     — all list[str] (raw UIDs)
  └─ (no methods; resolution to Member objects requires Group context — see Open Questions)

EventType (Enum)
  └─ AVAILABILITY, EVENT, RECURRING (extend as we encounter more)

Group(BaseModel + DictCompatMixin)
  ├─ uid, name, members: list[Member], subgroups: list[Subgroup], roles: list[Role]
  └─ methods: find_member(*, email=None, name=None, uid=None) -> Member | None

Subgroup, Role (BaseModel + DictCompatMixin)
  └─ uid, name (passive data, no methods)

Profile(BaseModel + DictCompatMixin)
  └─ uid, first_name, last_name (passive)

Post(BaseModel + DictCompatMixin)
  ├─ uid, title, body, timestamp, comments: list[dict]
  └─ (no methods yet; add_comment(...) deferred until we verify the Spond API supports it)

Comment — deferred to a follow-up
  └─ Modelling Post comments as a typed `Comment` class is on the roadmap
     but not in this PR; `Post.comments` currently exposes them as raw
     dicts (`list[dict[str, Any]]`).

Transaction(BaseModel + DictCompatMixin)
  └─ uid, paid_at, payment_name, paid_by_name (passive, Spond Club only)
```

Each typed model has a Pydantic `PrivateAttr` for the Spond/SpondClub client:

```python
_client: Optional["Spond"] = PrivateAttr(default=None)
```

Construction sites set this via a `from_api(data, client)` classmethod. PrivateAttr keeps it out of `model_dump()` and pdoc.

## Backward compatibility

### Dict-subscript shim

`DictCompatMixin` gives every typed model dict-like behaviour:

- `event["heading"]` works, emits `DeprecationWarning`
- `event["startTimestamp"]` works (alias-aware), emits `DeprecationWarning`
- `event.get("heading", default)` works, emits warning
- `"heading" in event` works
- `for key in event` iterates the API-field names (camelCase)
- `len(event)` returns the number of fields

Implementation: the mixin reads `cls.model_fields` to discover both the Python attribute name and the alias, and dispatches subscript access through to attribute access.

### Strict-equality test patterns

A small number of existing tests compare returned objects to raw dicts with `==`:

```python
assert g == {"id": "ID1", "name": "Event One"}
```

These need adapting to one of:

```python
assert g.uid == "ID1" and g.heading == "Event One"
# or
assert g.model_dump(by_alias=True) == {"id": "ID1", "heading": "Event One", ...}
```

This is part of the PR (one test class affected, ~5 assertions).

### Legacy write methods

`Spond.update_event`, `Spond.change_response`, `Spond.get_event_attendance_xlsx`, `Spond.send_message` stay in v1.x — they emit `DeprecationWarning` pointing at the new method, then delegate internally:

```python
async def update_event(self, uid: str, updates: JSONDict) -> JSONDict:
    warnings.warn(
        "Spond.update_event is deprecated; use Event.update() instead",
        DeprecationWarning,
        stacklevel=2,
    )
    event = await self.get_event(uid)
    return await event.update(**updates)
```

All four are removed in v2.0.

## Spond.get_* return-type changes

The seven methods that currently return `JSONDict` / `list[JSONDict] | None` change their return type but keep their names and signatures:

| Method | Before | After |
|---|---|---|
| `get_profile()` | `JSONDict` | `Profile` |
| `get_groups()` | `list[JSONDict] \| None` | `list[Group] \| None` |
| `get_group(uid)` | `JSONDict` | `Group` |
| `get_person(user)` | `JSONDict` | `Person` (concretely Member or Guardian) |
| `get_events(...)` | `list[JSONDict] \| None` | `list[Event] \| None` |
| `get_event(uid)` | `JSONDict` | `Event` |
| `get_posts(...)` | `list[JSONDict] \| None` | `list[Post] \| None` |
| `SpondClub.get_transactions(...)` | `list[JSONDict]` | `list[Transaction]` |

Dict-style consumers still work through the DictCompatMixin (with warning).

## Open questions (not blocking)

1. **Member ↔ UID resolution in Responses.** `Event.responses.accepted_uids` is `list[str]` not `list[Member]`. Resolving requires Group context, which Events only have via `recipients`/`groupId`. Add a helper `await event.accepted_members(spond)` that fetches the group and walks members — lazy, opt-in, no surprise HTTP from attribute reads.
2. **Guardian.managed_member.** If the API doesn't expose a back-link, Guardian is constructed inside `Member.guardians` and the parent reference can be added post-hoc by the Member constructor. Decide during impl based on actual API shape.
3. **Post.add_comment.** Probe whether Spond's API supports comment-add via `POST sponds/posts/{uid}/comments` or similar. If yes, add the method; if no, document as read-only.
4. **Send-message semantics for Guardian vs Member.** Verify whether the message routes differently based on recipient kind — may require different payload shapes.

All four are answerable mid-impl with live API probing using credentials at `/home/olen/prog/spond-kalender/config.py`.

## Files

**New:**
- `spond/_compat.py` — `DictCompatMixin`
- `spond/event.py` — `Event`, `Responses`, `EventType`
- `spond/match.py` — `Match` (Event subclass), `MatchInfo`
- `spond/person.py` — `Person`, `Member`, `Guardian`
- `spond/group.py` — `Group`
- `spond/subgroup.py` — `Subgroup`
- `spond/role.py` — `Role`
- `spond/profile.py` — `Profile`
- `spond/post.py` — `Post` (Comment deferred — see Type Inventory above)

**Changed:**
- `spond/spond.py` — `get_*` methods return typed objects; legacy write methods get deprecation wrappers
- `spond/club.py` — `Transaction` model added; `get_transactions` returns `list[Transaction]`
- `pyproject.toml` — `pydantic = ">=2.0"` added to runtime deps
- `tests/test_spond.py` — strict-equality assertions adapted; new tests for ActiveRecord methods, dict-compat, inter-dependencies
- `README.md` — examples updated to OO style

## Out of scope

- `Spond.get_messages` and the chat machinery — chats are tangled, leave on the dict-based path. Possible v1.4 follow-up.
- Removing `self.events_update` (a pre-existing latent attribute that was already cleaned up before this PR — out of scope here).
- Adding new HTTP endpoints. This is a re-shaping of the existing surface only.
- Renaming any `Spond.get_*` method — name stability matters more than name perfection.

## Test plan

- All existing tests pass (with the strict-equality adaptations).
- New tests for each ActiveRecord method (HTTP-mocked, asserting URL + payload + return value).
- New tests for `DictCompatMixin`: subscript works, warning fires, alias-mapped subscripts work.
- New tests for inter-dep navigation: `group.members[0]` is a `Member`, `member.guardians[0]` is a `Guardian`, etc.
- Manual smoke test of `examples/manual_test_functions.py` against live API.

## Versioning

Land as v1.3 — minor bump (return-type change is technically breaking, but the DictCompatMixin makes it soft). Legacy `Spond.*_event*` methods removed in v2.0 after a grace period.

## Implementation notes for maintainers

### Periodic API field-drift audit

Spond keeps adding fields to its responses. The original SDK reverse-engineering captured what was visible at the time, but several models had accumulated gaps by the time the OO rewrite landed (Profile was missing 4 fields, Group was missing 17, Responses was missing 1). Two-thirds of those gaps were invisible to ordinary use because `extra="allow"` silently preserves unknown fields — they were stored on `__pydantic_extra__` but not surfaced in pdoc, attribute autocompletion, or static type-checking.

A periodic audit closes the gap. The technique is mechanical:

1. Authenticate a live `Spond` client against a real account.
2. For each modelled endpoint, fetch the raw response and compute `set(api_keys) - set(model_field_aliases)`.
3. Add any newly-discovered fields to the model with sentinel defaults (so the model stays resilient when the field eventually disappears too), with API aliases preserved, and a one-line docstring categorising each (user-facing vs internal).

`Spond.get_*` methods naturally surface the data needed for the audit, and `<ModelClass>.model_fields[name].alias or name` enumerates the model's expected key set. Re-run before each minor release, or whenever Spond ships a noticeable app update.

### Subclass identity in `Event.update()`

`Event.update()` builds the next instance via `type(self).from_api(new_data, self._client)` — **not** the literal `Event.from_api`. This preserves subclass identity for the `Match` subclass (and any future subclasses). Without `type(self)`, a `Match.update(...)` call returns a plain `Event`, the cache replacement loop writes the demoted instance, and subsequent `spond.get_event(uid)` silently serves the wrong type. Regression test: `TestMatch.test_match_update_preserves_match_type`.

### Read-only field policy on Event

`spond/event.py` defines `_EVENT_READ_ONLY_FIELDS` — a frozenset of Python field names that `Event.update()` strips from the POST payload before sending. The list mirrors the pre-OO `_EVENT_TEMPLATE` writable scope (with reasoning grouped by category: server-managed timestamps, derived flags, series wiring, nested sub-resources with their own endpoints). When adding new fields to `Event`, decide at declaration time whether they should be writable on update, and add them to the frozenset if not. `Match.match_info` deliberately does **not** appear in this set — score updates flow through `Event.update()`.

### Update-payload discipline: `exclude_unset=True`

`Event.update()` dumps with `exclude_unset=True` (in addition to `exclude_none=True` and the read-only frozenset). This is the critical guard against round-tripping defaulted state back to Spond as authoritative. Pydantic's `model_fields_set` tracks exactly which fields were populated during validation — so a field that defaulted to `[]` (e.g. `owners`, `attachments`) or `None` because Spond's GET response didn't include it gets correctly excluded from the subsequent POST. Without this, calling `event.update(heading="X")` on an event whose source response omitted `owners` would send `"owners": []`, and Spond could interpret an explicit empty list as "clear all owners." Caller-supplied updates are overlaid on top of the dump, so explicit modifications always reach Spond regardless of source-data presence.
