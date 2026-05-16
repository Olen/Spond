# Spond
![spond logo](https://github.com/Olen/Spond/blob/main/images/spond-logo.png?raw=true)

Simple, unofficial library with some example scripts to access data from the [Spond](https://spond.com/) API.

## Install

`pip install spond`

### ⚠️ Upgrading to v2.0 — read this first

v2.0 is the OO-rewrite release. The `get_*` methods now return typed
Pydantic models (`Event`, `Group`, `Member`, `Post`, `Chat`, …) instead
of raw `dict`s. **Existing code that uses dict-style access keeps
working** through a `DeprecationWarning` shim — but a few things did
change. Before upgrading from 1.x:

- **Equality semantics changed.** `Event(uid="X") == Event(uid="X")`
  now compares natural keys (uid-based when present) rather than every
  field. Two instances with the same uid but different field state are
  now considered equal. Callers depending on the old "are these
  field-identical?" behaviour can use the new `obj.model_equals(other)`
  escape hatch.
- **Return types of every `Spond.get_*` method changed** from
  `JSONDict` / `list[JSONDict]` to typed objects. Static type checkers
  flag this; the runtime dict shim covers most code at runtime.
- **HTTP error class changed** from bare `ValueError` to `SpondAPIError`
  — which still inherits from `ValueError`, so `except ValueError:` is
  unaffected. Same for the `*NotFoundError` family (still `KeyError`).
- **Some deprecated wrappers will be removed in v3.x.**
  `Spond.update_event()`, `Spond.change_response()`, and
  `Spond.get_event_attendance_xlsx()` emit `DeprecationWarning` in v2.x;
  use `Event.update()`, `Event.change_response()`, and
  `Event.attendance_xlsx()` instead.

**Pin to `< 2.0.0` if you aren't ready to upgrade yet:**

```shell
pip install "spond<2.0.0"
```

Or in `pyproject.toml`:
```toml
[tool.poetry.dependencies]
spond = "<2.0.0"
```

Or `requirements.txt`:
```
spond<2.0.0
```

**Audit your code before upgrading** by running with deprecation
warnings promoted to errors — every dict-style access site lights up
so you can migrate it:

```shell
python -W error::DeprecationWarning your_script.py
```

The full migration story (semantics, write surface, exception
hierarchy, async context manager, etc.) is in
[`DESIGN-oo-rewrite.md`](DESIGN-oo-rewrite.md).

## Usage

You need a username and password from Spond

### Example code

```python
import asyncio
from spond import spond

username = 'my@mail.invalid'
password = 'Pa55worD'
group_id = 'C9DC791FFE63D7914D6952BE10D97B46'  # fake

async def main():
    async with spond.Spond(username=username, password=password) as s:
        group = await s.get_group(group_id)
        print(group.name)
        for member in group.members:
            print(f"  {member.full_name}")
            for guardian in member.guardians:
                print(f"    guardian: {guardian.full_name}")

asyncio.run(main())
```

> **Typed objects from v2.0 onwards.** `get_groups()`, `get_event()`,
> `get_posts()`, etc. now return typed `Group` / `Event` / `Post` objects
> with attribute access and per-instance methods. Existing dict-style
> access (`group["name"]`) still works with a `DeprecationWarning`
> through the v2.x line; the shim is removed in v3.0. See
> [`DESIGN-oo-rewrite.md`](DESIGN-oo-rewrite.md) for the full design and
> migration story.

### Working with the typed objects

```python
async with spond.Spond(username, password) as s:
    # Read: typed instances with attribute access
    event = await s.get_event(uid)
    print(event.heading, event.start_time, event.duration)

    # Convenience properties — synchronous, no HTTP
    if event.is_upcoming and not event.has_responded(my_uid):
        print("you haven't responded yet")

    # Resolve response uids to typed Member/Guardian objects
    for member in await event.accepted_members():
        print(f"  ✓ {member.full_name}")

    # Update via kwargs (returns a new instance)
    new_event = await event.update(heading="Renamed")

    # ActiveRecord-style write surface — same shape for Event and Post
    # (requires: from spond.event import Event; from spond.post import Post)
    new_event = Event(heading="My new event",
                     start_time=start, end_time=end, type="EVENT",
                     owners=[{"id": my_pid, "response": "accepted"}],
                     recipients={"group": {"id": group_id}})
    await new_event.save(client=s)   # POST → uid populated; cache updated
    assert new_event.uid

    new_event.description = "Some details"
    await new_event.save()           # mutate-in-place, then re-save

    await new_event.delete()         # DELETE → pruned from cache

    # Posts work the same way, with `add_comment` as a bonus:
    post = Post(uid="", type="PLAIN", group_uid=group_id,
                title="Hello", body="Welcome.")
    await post.save(client=s)
    comment = await post.add_comment("First!")
    assert comment.uid and comment.text == "First!"
    await post.delete()
```

### Identity / equality

Typed instances use natural-key equality so they behave correctly in
sets and as dict keys:

```python
a = await s.get_event(uid)
b = await s.get_event(uid)
assert a == b                  # same uid → equal, even if state differs
assert {a, b} == {a}           # dedups via __hash__

# Match is a subclass of Event; same uid → same entity
assert isinstance(match, Event)
assert match == event_with_same_uid
```

For callers who need the old field-by-field comparison (e.g. "has the
server state changed?"), use `model_equals(other)`.

### Exception hierarchy

```python
from spond import (
    SpondError,             # base — catch this for any SDK error
    AuthenticationError,    # login failures
    EventNotFoundError,     # also a KeyError, for backward compat
    GroupNotFoundError,     # also a KeyError
    PersonNotFoundError,    # also a KeyError
    SpondAPIError,          # HTTP failures; also a ValueError
)

try:
    event = await s.get_event(uid)
except EventNotFoundError:
    ...
```

Pre-OO `except KeyError:` / `except ValueError:` patterns continue to
work — the typed exceptions multi-inherit from the stdlib classes.

## Key methods

### get_groups()

Get details of all your group memberships and all members of those groups.

### get_events([group_id, subgroup_id, include_scheduled, max_end, min_end, max_start, min_start, max_events])

Get details of events, limited to 100 by default.
Optional parameters allow filtering by start and end datetimes, group and subgroup; more events to be returned; inclusion of 'scheduled' events.

### get_person()
Get a member's details.

### get_messages(max_chats=100)
Get chats, limited to 100 by default.
Optional parameter allows more events to be returned.

### send_message(text, user=None, group_uid=None, chat_id=None)
Send a message with content `text`.
Either specify an existing `chat_id`, or both `user` and `group_uid` for a new chat.

### get_event_attendance_xlsx()
Get Excel attendance report for a single event, available via the web client.

### change_response()
Change a member's response for an event (e.g. accept/decline)

### get_posts()
Retrieve posts from group walls.

### get_profile()
Retrieve information connected to the user's account.

## Example scripts

The following scripts are included in `examples/`.  Some of the scripts might require additional packages to be installed (csv, ical etc).

Rename the file `config.py.sample` to `config.py` and add your username and password to the file before running the samples.

### ical.py
Generates an ics-file of upcoming events.

### groups.py
Generates a json-file for each group you are a member of.

### attendance.py &lt;-f from_date&gt; &lt;-t to_date&gt; [-a]
Generates a csv-file for each event between `from_date` and `to_date` with attendance status of all organizers.  The optional parameter `-a` also includes all members that has been invited.

### transactions.py
Generates a csv-file for transactions / payments appeared in [Spond Club](https://www.spond.com/spond-club-overview/) > Finance > Payments.

### manual_test_functions.py
Demonstrates most `get...()` methods.

## AsyncIO
[Asyncio](https://docs.python.org/3/library/asyncio.html) might seem intimidating in the beginning, but for basic stuff, it is quite easy to follow the examples above, and just remeber to prefix functions that use the API with `async def ...` and to `await` all API-calls and all calls to said functions.

[This article](https://realpython.com/async-io-python/) will give a nice introduction to both why, when and how to use asyncio in projects.

## API documentation

The library's API documentation is generated from the docstrings in `spond/`
using [pdoc](https://pdoc.dev/) and published to GitHub Pages on every push
to `main`:

**[https://olen.github.io/Spond/](https://olen.github.io/Spond/)**

To browse the same docs locally (useful when iterating on docstrings),
install the dev dependencies and start the pdoc dev server:

```shell
poetry install
poetry run pdoc --docformat numpy ./spond
```

A browser tab opens at `http://localhost:8080` with a searchable, navigable
view of all public modules, classes, and methods, and a "View Source" link
next to each one. Pages update automatically when the docstrings change.

To generate static HTML instead:

```shell
poetry run pdoc --docformat numpy -o docs/ ./spond
```

The `--docformat numpy` flag parses NumPy-style `Parameters`, `Returns`, and
`Raises` sections as structured lists — omit it and the param list renders as
one flat paragraph.

The leading `./` is important when developing inside the repo — without it,
pdoc would document the *installed* `spond` package from `site-packages`
rather than your local checkout.

## Contributing

### Keeping a PR up to date with `main`

Add the `updateme` label to a PR targeting `main` and a GitHub Actions workflow will automatically merge `main` into the PR branch every time `main` advances. This is opt-in: PRs without the label are left alone.

Limitations:
- Only acts on PRs whose base branch is `main`. PRs targeting other branches are ignored even with the label.
- Only works for PRs from branches in this repository. PRs from forks cannot be pushed to via the workflow's token and will be skipped (the workflow logs which PRs it skipped).
- If `gh pr update-branch` fails for a given PR (merge conflict, branch protection rule, transient API error, etc.), that PR is skipped for this run and the failure is logged. The label stays on, so the next push to `main` will retry automatically.
