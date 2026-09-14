"""FastMCP server exposing ESPN fantasy football tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastmcp import FastMCP
from fastmcp.apps import PrefabAppConfig, ResourceCSP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult

from fantasy_mcp.cards import player_card
from fantasy_mcp.config import ConfigError, load_settings
from fantasy_mcp.espn import EspnClient, EspnError
from fantasy_mcp.filters import (
    FilterError,
    free_agent_filter,
    normalize_position,
    player_card_filter,
    player_ids_filter,
)
from fantasy_mcp.players import resolve_player
from fantasy_mcp.shapes import (
    find_matchup,
    shape_free_agent,
    shape_league_settings,
    shape_matchup,
    shape_player_card,
    shape_projections,
    shape_team,
    shape_whoami,
    team_by_id,
)

INSTRUCTIONS = """\
Read-only access to the user's ESPN fantasy football league.

Use these tools for any question about the user's team or league rather than
answering from memory. Call get_my_team before giving lineup, start/sit, or
roster advice, and base the advice on the roster and injury statuses it returns.

Use get_matchup for anything about this week's game: score, projection, win
probability, opponent, or per-player points. Use get_free_agents for pickup,
waiver, or "who's available" questions, and compare candidates against the
roster from get_my_team before recommending a move. Use get_player for
questions about a specific player (history, outlook, who owns them); pass
player_id from another tool's output when you have it. Only whoami,
get_league_settings, get_my_team, get_matchup, get_projections, get_free_agents,
and get_player exist. There is no standings, transaction, or past-week matchup
data yet -- say so instead of inventing it.

For start/sit or "set my lineup", call get_projections (pass next week's
number once this week's games have started) and present its changes; it
already applies this league's lineup slots. Call get_league_settings before
pickup or trade advice so recommendations use this league's scoring (PPR or
not) and roster limits; its result is stable for the season, so one call per
conversation is enough.

Nothing here can modify the team. If the user asks to make a move, describe
what to do and let them do it on ESPN.

If a tool fails with a message mentioning "cookies", the user's ESPN session
cookies have expired: tell them to re-copy espn_s2 and SWID from their browser
into wherever the server is configured: the extension's settings in Claude
Desktop (Settings → Extensions → ESPN Fantasy Football), or the .env file for
a local checkout.
"""

logger = logging.getLogger(__name__)
ESPN_CDN = "https://a.espncdn.com"

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


_players_index: list[dict[str, Any]] | None = None


def _get_players_index(client: EspnClient) -> list[dict[str, Any]]:
    """ESPN's active-player index, fetched once per process (used for name lookup)."""
    global _players_index
    if _players_index is None:
        _players_index = client.get_players_index()
    return _players_index


def set_players_index_for_tests(index: list[dict[str, Any]] | None) -> None:
    global _players_index
    _players_index = index


_pro_schedules: dict[str, Any] | None = None


def _get_pro_schedules(client: EspnClient) -> dict[str, Any]:
    """ESPN's NFL schedule/bye table, fetched once per process.

    Kickoff times can be flexed by the NFL mid-season; a long-lived process
    will keep the times it first saw. Restart the server to refresh.
    """
    global _pro_schedules
    if _pro_schedules is None:
        _pro_schedules = client.get_pro_schedules()
    return _pro_schedules


def set_pro_schedules_for_tests(schedules: dict[str, Any] | None) -> None:
    global _pro_schedules
    _pro_schedules = schedules


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
def get_league_settings() -> dict[str, Any]:
    """League rules: scoring, roster construction, schedule/playoffs, waivers, trades.

    Call this before start/sit, pickup, or trade advice so recommendations use
    this league's scoring (scoring.ppr = points per reception; scoring.summary
    is a one-line description; scoring.rules maps stat names -- the same names
    get_player's game log uses -- to points, with unmapped ESPN ids as stat_<id>).
    roster.lineup gives starting slots and bench/IR counts; roster.position_limits
    caps how many of a position a team may roster. waivers describes the claim
    system (budget is FAAB dollars when present); trades.deadline is a UTC date.
    """
    try:
        client = _get_client()
        return shape_league_settings(client.get("mSettings"))
    except (EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e


@mcp.tool
def get_my_team() -> dict[str, Any]:
    """Return the user's fantasy team: season record, points, and full roster.

    Each roster row has: player_id (pass to get_player); name; position (the
    player's NFL position, e.g. QB/RB/WR);
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
    fields as get_my_team (player_id, name, position, slot, pro_team, injury_status) plus
    points (scored so far this week) and projected (ESPN's projection for this
    player this week; null if unavailable). Only rows whose slot is not BENCH or IR
    count toward score.
    """
    try:
        client = _get_client()
        league = client.get("mMatchup", "mMatchupScore", "mTeam")
        team_id = client.find_my_team_id(league)
        week = league.get("status", {}).get("currentMatchupPeriod")
        if week is None:
            raise EspnError("ESPN response is missing status.currentMatchupPeriod.")
        game = find_matchup(league, team_id, week)
        return shape_matchup(game, league, team_id)
    except (EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e


MAX_WEEK = 18


@mcp.tool
def get_projections(week: int | None = None) -> dict[str, Any]:
    """ESPN projections for the user's roster for one NFL week, with a suggested optimal lineup.

    Use this for "set my lineup", "start X or Y?", or "who's on bye?". week
    defaults to current_week (the league's current NFL week, which ESPN keeps
    until the week's games finish); to plan ahead once games have kicked off,
    call again with week = current_week + 1. Projections are null until ESPN
    publishes them.

    players: every rostered player with slot (current lineup slot), opponent
    ("@KC" away, "vs KC" home, "BYE"), kickoff (UTC), and projected (ESPN's
    points projection for that week; null if ESPN has none). suggested_lineup
    fills this league's starting slots (including FLEX/superflex slots and
    their eligibility rules) to maximize projected points; players on IR or
    marked OUT/suspended are never started. changes lists who to start (with
    their suggested slot) and who to sit (with their current slot) to get
    there, plus the projected gain; a continuing starter that merely moves
    slots appears only in suggested_lineup. Present changes to the user rather
    than the whole table when they ask for lineup advice.
    """
    if week is not None and not 1 <= week <= MAX_WEEK:
        raise ToolError(f"week must be between 1 and {MAX_WEEK} (got {week}).")
    try:
        client = _get_client()
        league = client.get("mRoster", "mSettings")
        team_id = client.find_my_team_id(league)
        entries = (team_by_id(league, team_id).get("roster") or {}).get("entries") or []
        counts = {
            int(slot): count
            for slot, count in ((league.get("settings") or {}).get("rosterSettings") or {})
            .get("lineupSlotCounts", {})
            .items()
        }
        current_week = league.get("scoringPeriodId")
        if current_week is None:
            raise EspnError("ESPN response is missing scoringPeriodId.")
        target_week = week or current_week
        ids_ = [e.get("playerId") for e in entries if e.get("playerId") is not None]
        proj = client.get(
            "kona_player_info", fantasy_filter=player_ids_filter(ids_), scoring_period=target_week
        )
        schedules = _get_pro_schedules(client)
        return shape_projections(
            target_week,
            entries,
            proj.get("players") or [],
            schedules,
            counts,
            season=league.get("seasonId", client.settings.season),
            current_week=current_week,
        )
    except (FilterError, EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e


@mcp.tool
def get_free_agents(
    position: str | None = None,
    limit: int = 10,
    sort: str = "owned",
) -> dict[str, Any]:
    """List available players (free agents and waiver claims) in the user's league.

    Use this for "who should I pick up?", "best available RB", or "who's trending".

    Args: position -- one of QB, RB, WR, TE, K, D_ST (case-insensitive; D/ST also
    accepted); omit for all positions. limit -- 1 to 50, default 10. sort --
    "owned" (most rostered across ESPN first, default) or "projected" (highest
    season projection first).

    Each player row: player_id (pass to get_player), name, position, pro_team,
    injury_status, status (FREEAGENT =
    add immediately; WAIVERS = must submit a claim), percent_owned (% of ESPN
    leagues rostering them), percent_change (ownership trend -- positive means
    being picked up), season_projected / season_points (full-season projected /
    scored so far), week_projected / week_points (current NFL week; 0.0 may mean
    not played yet OR played and scored nothing), and positional_rank (ESPN's
    season rank at their position; null if unavailable). Next-week projections
    are not available from this tool.
    """
    try:
        client = _get_client()
        fantasy_filter = free_agent_filter(
            season=client.settings.season, position=position, limit=limit, sort=sort
        )
        league = client.get("kona_player_info", "mStatus", fantasy_filter=fantasy_filter)
        period = league.get("scoringPeriodId")
        if period is None:
            raise EspnError("ESPN response is missing scoringPeriodId.")
        season = league.get("seasonId", client.settings.season)
        players = [shape_free_agent(e, period, season) for e in league.get("players", [])]
        return {
            "week": period,
            "position": normalize_position(position) if position else None,
            "sort": sort,
            "players": players,
        }
    except (FilterError, EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e


@mcp.tool(app=PrefabAppConfig(csp=ResourceCSP(resource_domains=[ESPN_CDN])))
def get_player(name: str | None = None, player_id: int | None = None) -> ToolResult:
    """Full profile for one player: status, league ownership, season numbers, outlook, game log.

    Use this for "tell me about X", "how has X been doing", "who has X in my
    league", or "is X worth a claim". Pass exactly one of: name (full name is
    best; a partial name works if it matches one active player) or player_id
    (from any other tool's rows -- prefer this when you have it).

    Returns: player_id, name, position, pro_team, injury_status, injured,
    eligible_slots; league_status (ONTEAM / FREEAGENT / WAIVERS) and owned_by
    (the league team rostering them, or null); ownership across all ESPN leagues
    (percent_owned, percent_started, percent_change = trend, adp); season
    {year, projected, points, positional_rank}; last_season {year, points};
    outlook (ESPN's written preseason summary); game_log newest first, each
    week with points, projected (null until ESPN publishes it), and stats --
    raw counts such as rush_yds, targets, pass_td, fg_made_40_49, dst_sacks
    (zero-valued stats omitted). Covers this season and last. No news
    articles or opponent-matchup ratings. Name lookup uses a snapshot of ESPN's
    active-player list taken when the server started; a player signed since then
    may not resolve by name but still works by player_id. In clients that
    support MCP Apps this renders as a card; the JSON profile is always
    returned as text. headshot_url points at ESPN's CDN (team logo for a D/ST)
    and is not verified to exist.
    """
    if (name is None) == (player_id is None):
        raise ToolError("Pass exactly one of name or player_id.")
    try:
        client = _get_client()
        if player_id is None:
            player_id = resolve_player(name, _get_players_index(client))
        fantasy_filter = player_card_filter(player_id, season=client.settings.season)
        league = client.get("kona_playercard", "mTeam", "mStatus", fantasy_filter=fantasy_filter)
        entries = league.get("players") or []
        if not entries:
            raise EspnError(f"ESPN returned no player with id {player_id}.")
        league.setdefault("seasonId", client.settings.season)
        profile = shape_player_card(entries[0], league)
        text = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
        try:  # build AND serialize the card here; a presentation bug must never cost the data
            return ToolResult(content=text, structured_content=player_card(profile))
        except Exception:
            logger.exception("player_card failed to render; returning JSON only")
            return ToolResult(content=text)
    except (FilterError, EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
