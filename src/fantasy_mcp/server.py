"""FastMCP server exposing ESPN fantasy football tools."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from fantasy_mcp.config import ConfigError, load_settings
from fantasy_mcp.espn import EspnClient, EspnError
from fantasy_mcp.shapes import find_matchup, shape_matchup, shape_team, shape_whoami, team_by_id

INSTRUCTIONS = """\
Read-only access to the user's ESPN fantasy football league.

Use these tools for any question about the user's team or league rather than
answering from memory. Call get_my_team before giving lineup, start/sit, or
roster advice, and base the advice on the roster and injury statuses it returns.

Use get_matchup for anything about this week's game: score, projection, win
probability, opponent, or who has played. Only whoami, get_my_team, and
get_matchup exist. There is no standings, free agent, transaction, or
past-week data yet -- say so instead of inventing it.

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


@mcp.tool
def get_matchup() -> dict[str, Any]:
    """Return the user's current-week head-to-head matchup with live scoring.

    Use this for "am I winning?", "who am I playing?", or "should I have started
    X?". Covers the current week only. There is no per-player game-state field:
    points of 0.0 may mean the player has not played yet OR played and scored
    nothing -- do not claim to know which.

    Top level: week; status (UPCOMING, IN_PROGRESS, or FINAL); is_home; my_team;
    opponent. Each team has: team_id, name, abbrev, score (fantasy points so far
    this week), projected (ESPN's live projection for the week's final score),
    win_probability (0-1, may be null), and roster. Each roster row has the same
    fields as get_my_team (name, position, slot, pro_team, injury_status) plus
    points (scored so far this week) and projected (ESPN's projection for this
    player this week; null if unavailable). Only rows whose slot is not BENCH or IR
    count toward score.
    """
    try:
        client = _get_client()
        league = client.get("mMatchup", "mMatchupScore", "mTeam")
        team_id = client.find_my_team_id(league)
        week = league.get("status", {}).get("currentMatchupPeriod")
        game = find_matchup(league, team_id, week)
        return shape_matchup(game, league, team_id)
    except (EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
