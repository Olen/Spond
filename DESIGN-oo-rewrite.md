# Spond OO rewrite — design

**Status:** implementation complete on branch `feat/oo-rewrite`; under review
**Last updated:** 2026-05-14
**Scope:** First-class typed objects with ActiveRecord behaviour, replacing the dict-based return surface across `spond.spond.Spond` and `spond.club.SpondClub`. v2.0 also delivers the symmetric write surface (`Event.save()`/`delete()`), an exception hierarchy, natural-key equality, convenience properties, and async context-manager support.

## Feedback welcome

This document captured the design as it was brainstormed, and has been kept in sync with what shipped. The shape, deprecation path, and inventory in this file now reflect the implementation merged onto `feat/oo-rewrite`. The "Open questions" section near the end lists what was deliberately deferred to a follow-up release.

- **For high-level concerns** (API shape, scope, deprecation path) — open an issue titled `OO rewrite: …` or comment on the tracking PR.
- **For deeper design questions** — see the "Open questions" section near the end.
- **For implementer-facing notes** (field-drift audit, subclass discipline, update-payload rules) — see "Implementation notes for maintainers" at the bottom.

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

Every typed model extends `DictCompatModel`, which itself extends Pydantic's `BaseModel`. The dict-compatibility shim and the `LenientDate` annotated type live in `spond/_compat.py`; everything below inherits from it.

```
Person (base, DictCompatModel)
  ├─ uid, first_name, last_name, email (optional), profile (optional),
  │  phone_number (optional)
  ├─ full_name (property)
  │
  ├─ Member(Person)
  │    ├─ email, date_of_birth (LenientDate — tolerates Spond's malformed
  │    │   "2012-03-99"-style values), created_time, guardians,
  │    │   role_uids, subgroup_uids, respondent, custom_fields (alias "fields")
  │    └─ methods: send_message(text, group_uid)
  │
  └─ Guardian(Person)
       └─ methods: send_message(text, group_uid)

Event(DictCompatModel)
  ├─ uid, heading, start_time, end_time, type: str (compared against EventType),
  │  owners, recipients, responses, comments, behalf_of_uids, ...
  │
  ├─ ActiveRecord methods:
  │   ├─ save(client=None)   — POST `/sponds/` (create) when uid empty,
  │   │                        POST `/sponds/{uid}` (update) when uid set.
  │   │                        Mutates self in place with the persisted state.
  │   ├─ delete()             — DELETE `/sponds/{uid}`, prunes from cache.
  │   ├─ update(_updates=None, /, **fields) — returns a new instance
  │   │                                       with the updates applied.
  │   ├─ change_response(member_uid, *, accepted, decline_message=None)
  │   └─ attendance_xlsx() -> bytes
  │
  ├─ Async helpers (resolve uid lists to typed Member/Guardian via the
  │  client's group cache; lazy):
  │   ├─ accepted_members()
  │   ├─ declined_members()
  │   ├─ unanswered_members()
  │   ├─ waiting_list_members()
  │   └─ unconfirmed_members()
  │
  ├─ Synchronous convenience properties / methods (pure-Python, no HTTP):
  │   ├─ is_past, is_upcoming, duration
  │   ├─ has_responded(uid), response_for(uid)
  │   └─ url (canonical Spond web URL)
  │
  └─ Match(Event)  — sports fixtures
       ├─ match_info: MatchInfo | None  — team/opponent names, scores, HOME/AWAY
       └─ Spond.get_events() / get_event() return Match (not plain Event)
          when the API record has matchEvent=True. Dispatch lives in
          spond.spond._typed_event.

Responses (sub-object of Event)
  ├─ accepted_uids, declined_uids, unanswered_uids, waiting_list_uids,
  │  unconfirmed_uids — all list[str] (raw UIDs)
  ├─ decline_messages: dict
  └─ (no methods; resolution to Member objects requires Group context —
     see Open Questions)

EventType (StrEnum, canonical reference)
  └─ AVAILABILITY, EVENT, RECURRING
     The `Event.type` field itself stays a `str` so Spond can introduce
     new variants without crashing validation; EventType is a typed lookup
     for callers writing comparisons.

Group(DictCompatModel)
  ├─ uid, name, members: list[Member], subgroups: list[Subgroup], roles: list[Role],
  │  plus the full set of fields surfaced by the live API audit
  │  (created_time, member_permissions, guardian_permissions, chat_age_limit,
  │  share_contact_info, address_format, ...)
  └─ methods: find_member(*, email=None, name=None, uid=None) -> Member | None
              (`from_api` wires `_client` through nested Members/Guardians)

Subgroup, Role (DictCompatModel)
  └─ uid, name (passive data, no methods)

Profile(DictCompatModel)
  └─ uid, first_name, last_name, plus the live-audited extras (passive)

Post(DictCompatModel)
  ├─ uid, title, body, timestamp, group_uid, owner_uid,
  │  subgroup_uids, visibility, comments: list[Comment], reactions, …
  └─ ActiveRecord methods:
       ├─ save(client=None)   — POST `/posts/` (create) when uid empty,
       │                        POST `/posts/{uid}` (update) when uid set.
       │                        Mutates self in place with the persisted state.
       ├─ delete()             — DELETE `/posts/{uid}`, prunes from cache.
       └─ add_comment(text)    — POST `/posts/{uid}/comments`, returns the
                                 new `Comment` and appends to self.comments.

Comment(DictCompatModel) — typed sub-object of Post and Event
  ├─ uid, from_profile_uid, timestamp, text, reactions
  └─ (no methods; comment edit/delete endpoints aren't exposed by the
     consumer API. Comment lifecycle goes through the parent —
     `post.add_comment(text)`.)

Chat(DictCompatModel)
  ├─ uid, name, type, participants, newest_timestamp, unread, muted,
  │  community, message: Message | None
  └─ methods: send(text) -> dict
     (Routes through the chat-server host and chat-auth token; lazy
     handshake on first call via the existing `Spond._login_chat`.)

Message(DictCompatModel) — sub-object of Chat (most-recent message only)
  ├─ chat_id, msg_num, type: str, timestamp, reactions, text, user
  └─ type-specific optional payload fields: new_name (RENAME), images (IMAGES),
     internal_promo (INTERNAL_PROMO), campaign (CAMPAIGN), spond (SPOND).
     Anything Spond adds later passes through extra="allow".

Comment — deferred to a follow-up (still applies)
  └─ `Post.comments` exposes them as raw dicts (`list[dict[str, Any]]`).

Transaction(DictCompatModel)
  └─ uid, paid_at, payment_name, paid_by_name (passive, Spond Club only;
     uses extra="allow" like every other top-level type for forward-compat).
```

Each typed model with operations carries a Pydantic `PrivateAttr` for the Spond/SpondClub client:

```python
_client: Any = PrivateAttr(default=None)
```

Construction sites set this via a `from_api(data, client)` classmethod. `PrivateAttr` keeps it out of `model_dump()` and pdoc. Passive types (Subgroup, Role, Profile, Responses, MatchInfo) omit the client since they don't issue HTTP themselves.

## Identity / equality

`DictCompatModel.__eq__` and `__hash__` are driven by a `_natural_key()` hook each typed model overrides. The default uses `(entity_kind, uid)` where `entity_kind` walks the MRO to find the closest user-defined ancestor before `DictCompatModel` — so `Match("X") == Event("X")` (both resolve to kind `"Event"`), and same for `Member`/`Guardian` → `"Person"`.

When `uid` is absent (a freshly-constructed instance not yet persisted), each model provides a fallback derived from user-visible fields:

| Entity      | Fallback key                              |
|-------------|-------------------------------------------|
| Event       | heading + start_time                      |
| Group       | name                                      |
| Person/Member/Guardian | full_name + email              |
| Profile     | full_name                                 |
| Post        | title + timestamp                         |
| Chat        | name + type                               |
| Transaction | paid_at + payment_name + paid_by_name     |
| Subgroup    | name                                      |
| Role        | name                                      |
| Message     | (chat_id, msg_num) — no uid at all        |

This makes typed instances usable as set members and dict keys following the ORM "same uid → same entity" convention. For callers who need the pre-OO field-by-field equality (e.g. "has the server-side state changed?"), `model_equals(other)` returns the Pydantic default.

## Exception hierarchy

```
SpondError                          (base)
├── AuthenticationError             (login failures)
├── SpondAPIError, ValueError       (HTTP failures; carries status/body/url)
└── SpondNotFoundError, KeyError    (lookup-by-id failures)
    ├── EventNotFoundError
    ├── GroupNotFoundError
    ├── PersonNotFoundError
    └── ChatNotFoundError
```

`SpondAPIError` multi-inherits from `ValueError`; `*NotFoundError` types multi-inherit from `KeyError`. Pre-OO `except KeyError:` and `except ValueError:` patterns keep working.

`AuthenticationError` lives in `spond.exceptions` but is re-exported from `spond.__init__`, so `from spond import AuthenticationError` keeps working.

## Async context manager

`Spond` and `SpondClub` are async context managers via `_SpondBase.__aenter__` / `__aexit__`. The idiomatic shape:

```python
async with Spond(username, password) as s:
    events = await s.get_events()
# clientsession closed automatically on exit, even if the body raised
```

`__aexit__` wraps the close in `contextlib.suppress(RuntimeError)` so a caller that manually closed the session inside the `with` block doesn't trigger a second-close that masks the original control flow.

## Backward compatibility

### Dict-subscript shim

`DictCompatModel` (in `spond/_compat.py`) gives every typed model dict-like behaviour:

- `event["heading"]` works, emits `DeprecationWarning`
- `event["startTimestamp"]` works (alias-aware), emits `DeprecationWarning`
- `event.get("heading", default)` works, emits warning
- `"heading" in event` works
- `for key in event` iterates the API-field names (camelCase) actually populated on this instance
- `len(event)` returns the same count as the iterator
- `keys()` / `values()` / `items()` mirror dict semantics, scoped to populated fields

Implementation: the base class reads `cls.model_fields` to discover both the Python attribute name and the alias, then routes subscript access through to attribute access. The "what's actually present" view is built from `model_fields_set ∪ __pydantic_extra__` so iteration and `len()` reflect only fields that were populated from the source data — fields sitting at their default values don't leak into the dict-compat surface.

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

`Spond.update_event`, `Spond.change_response`, `Spond.get_event_attendance_xlsx` stay in v1.x — they emit `DeprecationWarning` pointing at the new method, then delegate internally. `Spond.send_message` is **not** deprecated: it remains the entrypoint for sending a one-off message to a user (the chat-thread send is exposed on `Chat.send(text)` for callers already holding a `Chat` object).

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

The three deprecated wrappers are removed in v3.0 (or a later v2.x), after callers have had a grace period to migrate.

## Spond.get_* return-type changes

Every `get_*` method now returns typed objects; names and signatures are unchanged:

| Method | Before | After |
|---|---|---|
| `get_profile()` | `JSONDict` | `Profile` |
| `get_groups()` | `list[JSONDict] \| None` | `list[Group] \| None` |
| `get_group(uid)` | `JSONDict` | `Group` |
| `get_person(user)` | `JSONDict` | `Person` (concretely Member or Guardian) |
| `get_events(...)` | `list[JSONDict] \| None` | `list[Event] \| None` (`Match` for match events) |
| `get_event(uid)` | `JSONDict` | `Event` or `Match` |
| `get_posts(...)` | `list[JSONDict] \| None` | `list[Post] \| None` |
| `get_messages(...)` | `list[JSONDict] \| None` | `list[Chat] \| None` |
| `SpondClub.get_transactions(...)` | `list[JSONDict]` | `list[Transaction]` |

Dict-style consumers still work through `DictCompatModel` (with warning).

## Open questions / follow-up

Items deferred from this PR, tracked here as roadmap candidates.

1. **`Group.invite_member()` / `Group.save()`.** Group management (inviting members, editing group settings) is read-only. The invitation flow in particular goes through `/invites` rather than `/groups/{uid}/members` and needs careful probing.
2. **Guardian.managed_member back-link.** Not yet exposed. Guardians are currently constructed inside `Member.guardians`; a post-hoc parent reference can be added if a downstream caller asks for it.
3. **Full chat history.** `Chat.message` only carries the most-recent message; the chat API has additional endpoints for older messages that aren't modelled yet.
4. **Comment edit / delete.** Spond's app supports editing and deleting your own comments, but the corresponding endpoints aren't yet probed/modelled. `post.add_comment(text)` ships in v2.0; the lifecycle endpoints (`PUT /posts/{uid}/comments/{cuid}`, `DELETE /posts/{uid}/comments/{cuid}` or similar) need verification.

All four remain answerable with live API probing against a real Spond account.

## What shipped in v2.0 (previously open)

These items were "open questions" in earlier revisions of this document and have since landed:

- **`Event.accepted_members()` and siblings** — async helpers resolving each `responses.*_uids` list to typed `Member`/`Guardian` objects via the client's group cache (lazy fetch when empty). Five variants: `accepted_members`, `declined_members`, `unanswered_members`, `waiting_list_members`, `unconfirmed_members`.
- **`Event.save()` and `Event.delete()`** — symmetric ActiveRecord write surface. `save()` dispatches on `self.uid` (create vs update) and mutates self in place; `delete()` issues DELETE and prunes the cache. Endpoints verified live: POST `/sponds/` for create, DELETE `/sponds/{uid}` for delete. The `recipients` field (which is in `_EVENT_READ_ONLY_FIELDS` for the update path) is allowed through on create since Spond requires it.
- **Custom exception hierarchy** — `SpondError` base; `EventNotFoundError`/`GroupNotFoundError`/`PersonNotFoundError`/`ChatNotFoundError` (all also `KeyError`); `SpondAPIError` (also `ValueError`). Pre-OO `except KeyError:` / `except ValueError:` patterns preserved.
- **Natural-key equality** — `__eq__`/`__hash__` driven by `_natural_key()` on each typed model. uid-based when set, else user-visible-field fallback (heading+start_time for Event, etc.). `model_equals()` provides the old field-by-field shape for callers that need it.
- **Convenience properties on Event** — `is_past`, `is_upcoming`, `duration`, `has_responded(uid)`, `response_for(uid)`.
- **Async context manager on `Spond` / `SpondClub`** — `async with Spond(...) as s:` closes the aiohttp session automatically.
- **`Post.save()` / `Post.delete()` / `Post.add_comment()`** — symmetric write surface on Post, mirroring Event's. Endpoints verified live: POST `/posts/` for create, POST `/posts/{uid}` for update, DELETE `/posts/{uid}`, POST `/posts/{uid}/comments` for add_comment. `add_comment` returns a typed `Comment` and appends it to `post.comments` in place.
- **Typed `Comment` model** — `Post.comments` and `Event.comments` now contain `list[Comment]` instead of `list[dict]`. Same forward-compat (`extra="allow"`) and resilience-default discipline as the other types.

## Files

**New:**
- `spond/_compat.py` — `DictCompatModel`, `LenientDate`, natural-key equality machinery
- `spond/event.py` — `Event`, `Responses`, `EventType`, `_EVENT_READ_ONLY_FIELDS`, `save()`/`delete()` write surface, member-resolution helpers, convenience properties
- `spond/exceptions.py` — `SpondError` and the typed-exception hierarchy
- `spond/match.py` — `Match` (Event subclass), `MatchInfo`
- `spond/person.py` — `Person`, `Member`, `Guardian`
- `spond/group.py` — `Group`
- `spond/subgroup.py` — `Subgroup`
- `spond/role.py` — `Role`
- `spond/profile.py` — `Profile`
- `spond/post.py` — `Post` with `save()`/`delete()`/`add_comment()` ActiveRecord surface
- `spond/comment.py` — typed `Comment` model (used by `Post.comments` and `Event.comments`)
- `spond/chat.py` — `Chat`, `Message`

**Changed:**
- `spond/__init__.py` — re-exports the typed exception hierarchy alongside `AuthenticationError`
- `spond/base.py` — `_SpondBase.__aenter__` / `__aexit__` for async context manager support
- `spond/spond.py` — `get_*` methods return typed objects; legacy write methods get deprecation wrappers; `_typed_event` dispatches Event vs. Match; raise sites use typed exceptions
- `spond/club.py` — `Transaction` model added; `get_transactions` returns `list[Transaction]`
- `pyproject.toml` — `pydantic = ">=2.0"` added to runtime deps
- `README.md` — examples updated to OO style + async-with shape

**Tests:**
The previous monolithic `tests/test_spond.py` has been split by domain. The current layout:
- `tests/conftest.py` — shared fixtures and constants
- `tests/test_auth.py` — login flow + `require_authentication` decorator metadata
- `tests/test_backward_compat.py` — regression guards for pre-OO patterns (dict access, `except KeyError:`/`ValueError:`, top-level `AuthenticationError` import, deprecated wrappers)
- `tests/test_club.py` — `Transaction` and `SpondClub.get_transactions()`
- `tests/test_comment.py` — typed `Comment` model, materialisation on Post/Event
- `tests/test_compat.py` — `DictCompatModel` shim + `LenientDate`
- `tests/test_context_manager.py` — `async with Spond(...)` shape
- `tests/test_event_convenience.py` — `is_past`/`is_upcoming`/`duration`/`response_for`/`has_responded`
- `tests/test_event_members.py` — `accepted_members()` and siblings
- `tests/test_event_save_delete.py` — ActiveRecord write surface (`save()` create/update, `delete()`)
- `tests/test_events.py` — `get_event` / `get_events` HTTP path, deprecated wrappers, OO `Event` methods, `Match` subclass
- `tests/test_exceptions.py` — exception hierarchy + raise-site coverage
- `tests/test_export.py` — deprecated `get_event_attendance_xlsx` wrapper
- `tests/test_groups.py` — `get_group` + Group → Member → Guardian navigation + `get_person`
- `tests/test_identity.py` — natural-key equality / hashing across all models
- `tests/test_messaging.py` — `Spond.send_message` + `Chat`/`Message`
- `tests/test_post_save_delete.py` — ActiveRecord write surface on Post (`save()`, `delete()`, `add_comment()`)
- `tests/test_posts.py` — `get_posts` query construction, caching, error surfacing

## Out of scope

- Removing `self.events_update` (a pre-existing latent attribute that was already cleaned up before this PR).
- Adding new HTTP endpoints. This is a re-shaping of the existing surface only.
- Renaming any `Spond.get_*` method — name stability matters more than name perfection.

## Test plan (what shipped)

- All pre-existing tests pass (with strict-equality assertions adapted).
- ActiveRecord methods: HTTP-mocked tests asserting URL + payload + return value (`tests/test_events.py`, `tests/test_messaging.py`, `tests/test_export.py`).
- `DictCompatModel` shim: subscript works, warning fires, alias-mapped subscripts work, `__len__`/`__contains__`/`__iter__` agree (`tests/test_compat.py`).
- Inter-dep navigation: `group.members[0]` is a `Member`, `member.guardians[0]` is a `Guardian`, etc. (`tests/test_groups.py`).
- Subclass identity through update: `Match.update(...)` returns a `Match`, not a demoted `Event` (`tests/test_events.py::TestMatch::test_match_update_preserves_match_type`).
- Forward-compat: unmodelled fields survive a roundtrip via `extra="allow"` and are reachable through `__pydantic_extra__` (`tests/test_compat.py`).
- Manual smoke test of `examples/manual_test_functions.py` against the live API, plus the periodic field-drift audit (see implementation notes).

## Versioning

This work lands as **v2.0** — a major bump even though backward
compatibility is preserved through the deprecation cycle. The
rationale:

- **New equality semantics.** Two `Event(uid="X")` instances now
  compare equal regardless of field state — pre-v2.0 they did not.
  The `model_equals()` escape hatch preserves the old shape for
  callers who need it, but the default operator changed, and that's
  a behavioural break.
- **Substantial new surface.** Typed write methods (`save()`/
  `delete()`), exception hierarchy, member-resolution helpers,
  convenience properties, and async context-manager support are all
  net-new — calling this a "minor" feels wrong.
- **Return-type changes.** Every `Spond.get_*` method now returns
  typed objects instead of `dict[str, Any]` — softened by the
  dict-compat shim, but technically a breaking type change for any
  caller using static type checking.

The plan:

- **v2.0 (this release)** — ship everything described in this
  document, with full backward compatibility: `DictCompatModel` shim
  emits `DeprecationWarning` on dict-style access; `*NotFoundError`
  multi-inherits from `KeyError`; `SpondAPIError` multi-inherits
  from `ValueError`; deprecated wrappers (`Spond.update_event`/
  `change_response`/`get_event_attendance_xlsx`) still present and
  delegating with `DeprecationWarning`.
- **v2.x (later)** — start removing the compat shims behind feature
  flags or env vars, so callers can opt into the v3.0 surface early
  and find any code that still relies on the dict path.
- **v3.0** — remove the deprecation cycle: drop the dict-compat
  shim entirely, drop the multi-inheritance from `KeyError`/
  `ValueError` on the typed exceptions, remove the three deprecated
  wrapper methods.

Callers running v2.x with no deprecation warnings will have a
zero-change upgrade to v3.0.

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
