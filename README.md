# Spond
![spond logo](https://github.com/Olen/Spond/blob/main/images/spond-logo.png?raw=true)

Simple, unofficial library with some example scripts to access data from the [Spond](https://spond.com/) API.

## Install

`pip install spond`

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
    s = spond.Spond(username=username, password=password)
    group = await s.get_group(group_id)
    print(group.name)
    for member in group.members:
        print(f"  {member.full_name}")
        for guardian in member.guardians:
            print(f"    guardian: {guardian.full_name}")
    await s.clientsession.close()

asyncio.run(main())
```

> **Typed objects from v1.3 onwards.** `get_groups()`, `get_event()`, `get_posts()`,
> etc. now return typed `Group` / `Event` / `Post` objects with attribute access
> and per-instance methods (`event.update(...)`, `event.change_response(...)`,
> `member.send_message(...)`). Existing dict-style access (`group["name"]`)
> still works for one major version with a `DeprecationWarning`. See
> [`DESIGN-oo-rewrite.md`](DESIGN-oo-rewrite.md) for the full design and
> migration story.

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
