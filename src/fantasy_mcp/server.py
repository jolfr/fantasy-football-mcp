"""FastMCP server exposing ESPN fantasy football tools."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from fantasy_mcp import ids
from fantasy_mcp.config import ConfigError, Settings, load_settings
from fantasy_mcp.espn import EspnClient, EspnError

INSTRUCTIONS = """\
Read-only access to the user's ESPN fantasy football league.

Use these tools for any question about the user's team or league rather than
answering from memory. Call get_my_team before giving lineup, start/sit, or
roster advice, and base the advice on the roster and injury statuses it returns.

Only whoami and get_my_team exist. There is no matchup, standings, free agent,
or transaction data yet -- say so instead of inventing it.

Nothing here can modify the team. If the user asks to make a move, describe
what to do and let them do it on ESPN.

If a tool fails with a message mentioning "cookies", the user's ESPN session
cookies have expired: tell them to re-copy espn_s2 and SWID from their browser
into the server's .env file.
"""

mcp = FastMCP("fantasy-mcp", instructions=INSTRUCTIONS)

_client: EspnClient | None = None


def _get_client() -> EspnClient:
    global _client
    if _client is None:
        _client = EspnClient(load_settings())
    return _client


def set_client_for_tests(client: EspnClient | None) -> None:
    global _client
    _client = client


# --- shaping -----------------------------------------------------------------


def team_by_id(league: dict[str, Any], team_id: int) -> dict[str, Any]:
    for team in league.get("teams", []):
        if team.get("id") == team_id:
            return team
    raise EspnError(
        f"Team id {team_id} is not in this league. Check ESPN_TEAM_ID "
        "(or unset it to auto-detect your team)."
    )


def shape_whoami(league: dict[str, Any], team_id: int, settings: Settings) -> dict[str, Any]:
    team = team_by_id(league, team_id)
    return {
        "league_id": settings.league_id,
        "season": settings.season,
        "league_name": league.get("settings", {}).get("name"),
        "team_id": team_id,
        "team_name": team.get("name"),
    }


def _shape_player(entry: dict[str, Any]) -> dict[str, Any]:
    player = entry.get("playerPoolEntry", {}).get("player", {})
    return {
        "name": player.get("fullName"),
        "position": ids.name(ids.POSITIONS, player.get("defaultPositionId", -1)),
        "slot": ids.name(ids.LINEUP_SLOTS, entry.get("lineupSlotId", -1)),
        "pro_team": ids.name(ids.PRO_TEAMS, player.get("proTeamId", -1)),
        "injury_status": player.get("injuryStatus"),
    }


def _slot_sort_key(entry: dict[str, Any]) -> tuple[int, int]:
    slot = entry.get("lineupSlotId", 99)
    # Starters (anything not bench/IR) first, then bench, then IR.
    bucket = {20: 1, 21: 2}.get(slot, 0)
    return (bucket, slot)


def shape_team(team: dict[str, Any]) -> dict[str, Any]:
    overall = team.get("record", {}).get("overall", {})
    entries = sorted(team.get("roster", {}).get("entries", []), key=_slot_sort_key)
    return {
        "team_id": team["id"],
        "name": team.get("name"),
        "abbrev": team.get("abbrev"),
        "record": {
            "wins": overall.get("wins", 0),
            "losses": overall.get("losses", 0),
            "ties": overall.get("ties", 0),
        },
        "points_for": overall.get("pointsFor", 0.0),
        "points_against": overall.get("pointsAgainst", 0.0),
        "roster": [_shape_player(e) for e in entries],
    }


# --- tools -------------------------------------------------------------------


@mcp.tool
def whoami() -> dict[str, Any]:
    """Verify ESPN credentials and league configuration.

    Call this first. Cheap (one small request, no roster data). Returns the league
    id/name, season, and the user's team id/name. Fails with an explanatory
    message if cookies are expired or the league/team can't be resolved.
    """
    try:
        client = _get_client()
        league = client.get("mTeam", "mSettings")
        team_id = client.find_my_team_id(league)
        return shape_whoami(league, team_id, client.settings)
    except (EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e


@mcp.tool
def get_my_team() -> dict[str, Any]:
    """Return the user's fantasy team: season record, points, and full roster.

    Each roster row has: name; position (the player's NFL position, e.g. QB/RB/WR);
    slot (the fantasy lineup slot — BENCH and IR mean not starting, anything else
    is a starter); pro_team (NFL team abbreviation); injury_status. Rows are
    ordered starters first, then bench, then IR. Record and points are
    season-to-date for the configured season.
    """
    try:
        client = _get_client()
        league = client.get("mTeam", "mRoster")
        team_id = client.find_my_team_id(league)
        return shape_team(team_by_id(league, team_id))
    except (EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
