"""Typed `Match` model — a sports-fixture `Event` subclass.

A "match" in Spond is an Event with `matchEvent=True` plus a `matchInfo`
sub-object carrying opponent name, team name, scores, and home/away status.
`Spond.get_events()` and `Spond.get_event()` automatically return `Match`
instances (instead of plain `Event`) when the underlying API record has
`matchEvent=True`, so callers can `isinstance(event, Match)` to discriminate.

The `matchInfo` shape was verified against real Spond fixtures during
implementation.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from ._compat import DictCompatModel
from .event import Event


class MatchInfo(DictCompatModel):
    """Score and opponent metadata attached to a `Match`.

    All fields are optional with sensible defaults so a fixture without
    scores yet (the typical pre-match state) doesn't crash construction.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: str | None = None
    """`"HOME"` or `"AWAY"` — whether the team plays on its own ground."""

    team_name: str | None = Field(default=None, alias="teamName")
    """Name of the authenticated user's team for this fixture."""
    team_score: int | None = Field(default=None, alias="teamScore")
    """Goals/points scored by the user's team. `None` until scores entered."""

    opponent_name: str | None = Field(default=None, alias="opponentName")
    """Name of the opposing team."""
    opponent_score: int | None = Field(default=None, alias="opponentScore")
    """Goals/points scored by the opposing team. `None` until scores entered."""

    scores_set: bool = Field(default=False, alias="scoresSet")
    """True once any score is recorded (either team's) for this fixture."""
    scores_set_ever: bool = Field(default=False, alias="scoresSetEver")
    """Server-tracked: True if scores have ever been set, even if later cleared."""
    scores_final: bool = Field(default=False, alias="scoresFinal")
    """True once the result has been marked final (no further edits expected)."""
    scores_public: bool = Field(default=False, alias="scoresPublic")
    """True if the scores are visible to non-admin members of the group."""


class Match(Event):
    """A Spond Event that represents a sports fixture.

    Carries everything an `Event` does, plus `match_info` with the opponent
    and score metadata. Construct via `Spond.get_events()` /
    `Spond.get_event()` — they pick `Match` or `Event` automatically based
    on the underlying `matchEvent` flag.

    ```python
    events = await spond.get_events()
    for e in events:
        if isinstance(e, Match) and e.match_info:
            print(f"{e.match_info.team_name} {e.match_info.team_score} - "
                  f"{e.match_info.opponent_score} {e.match_info.opponent_name}")
    ```

    Updates to score fields go through the same `Event.update()` machinery:

    ```python
    match = await spond.get_event(uid)  # returns Match when matchEvent is true
    await match.update(matchInfo={"teamScore": 3, "opponentScore": 1,
                                  "scoresFinal": True})
    ```

    The `matchInfo` dict is forwarded to Spond verbatim; the score-related
    booleans `scoresSetEver` etc. are server-tracked so callers shouldn't
    set them directly.
    """

    match_info: MatchInfo | None = Field(default=None, alias="matchInfo")
    """Per-fixture opponent/score metadata. Always present in the API for a
    real match (`match_event=True`), but defaulted to `None` for resilience."""
