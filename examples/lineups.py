import asyncio

from config import password, username

from spond import spond

PITCH_WIDTH = 62
PITCH_HEIGHT = 21
LABEL_MAX = 11


def first_name(entry: dict) -> str:
    """First name of an assigned player, or a dash for an unfilled slot.

    A line-up can hold positions with no player assigned; those carry only
    coordinates, so `playerName` may be empty or missing entirely.
    """
    parts = (entry.get("playerName") or "").split()
    return parts[0] if parts else "-"


def pitch_rows(players: list[dict]) -> list[str]:
    """Lay players out on a text grid using their normalised coordinates.

    `x` and `y` both run 0.0-1.0, with `y` measured from the opponent's goal,
    so row 0 is the attacking end and the last row is the team's own goal.
    """
    grid = [[" "] * PITCH_WIDTH for _ in range(PITCH_HEIGHT)]
    filled = set()

    def place(row: int, col: int, label: str) -> None:
        """Write `label`, nudging it aside if that cell is already occupied."""
        for row_offset, col_offset in ((0, 0), (-1, 0), (1, 0), (0, 2), (0, -2)):
            r, c = row + row_offset, col + col_offset
            if not (0 <= r < PITCH_HEIGHT and 0 <= c <= PITCH_WIDTH - len(label)):
                continue
            if any((r, c + i) in filled for i in range(len(label) + 1)):
                continue
            for i, char in enumerate(label):
                grid[r][c + i] = char
                filled.add((r, c + i))
            return

    # Deepest players first, so the goalkeeper keeps its cell in a collision.
    for player in sorted(players, key=lambda p: p["y"], reverse=True):
        label = first_name(player)[:LABEL_MAX]
        row = round(player["y"] * (PITCH_HEIGHT - 1))
        col = round(player["x"] * (PITCH_WIDTH - 1)) - len(label) // 2
        place(row, max(0, min(col, PITCH_WIDTH - len(label))), label)

    halfway = PITCH_HEIGHT // 2
    grid[halfway] = ["-" if char == " " else char for char in grid[halfway]]
    return ["".join(row) for row in grid]


async def main() -> None:
    s = spond.Spond(username=username, password=password)

    formations = {f["id"]: f for f in await s.get_formations()}
    events = await s.get_events(max_events=100) or []

    for event in events:
        if not event.get("matchEvent"):
            continue
        for lineup in await s.get_lineups(event["id"]):
            formation = formations.get(lineup.get("formationId"))
            print(f"\n{event['heading']} - {event['startTimestamp'][:10]}")
            print(
                f"{lineup['name']}: "
                f"{formation['name'] if formation else 'no formation template'}"
            )
            print("+" + "-" * PITCH_WIDTH + "+  attacking")
            for row in pitch_rows(lineup["players"]):
                print(f"|{row}|")
            print("+" + "-" * PITCH_WIDTH + "+  own goal")
            substitutes = [first_name(p) for p in lineup["substitutes"]]
            if substitutes:
                print(f"Substitutes: {', '.join(substitutes)}")

    await s.clientsession.close()


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.run(main())
