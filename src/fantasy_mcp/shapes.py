"""Pure functions that shape ESPN league JSON into tool output."""

from __future__ import annotations

from typing import Any

from fantasy_mcp import ids
from fantasy_mcp.config import Settings
from fantasy_mcp.espn import EspnError

PROJECTION_SOURCE_ID = 1  # player.stats[].statSourceId: 1 = projected, 0 = actual


def _find_team(league: dict[str, Any], team_id: int | None) -> dict[str, Any] | None:
    for team in league.get("teams", []):
        if team.get("id") == team_id:
            return team
    return None


def team_by_id(league: dict[str, Any], team_id: int) -> dict[str, Any]:
    team = _find_team(league, team_id)
    if team is not None:
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


def find_matchup(league: dict[str, Any], team_id: int, period: int) -> dict[str, Any]:
    """Return the schedule entry for ``period`` in which ``team_id`` plays."""
    for game in league.get("schedule", []):
        if game.get("matchupPeriodId") != period:
            continue
        sides = (game.get("home", {}).get("teamId"), game.get("away", {}).get("teamId"))
        if team_id in sides:
            return game
    raise EspnError(f"No matchup for your team in week {period} (bye week?).")


def _round(value: Any) -> float | None:
    return None if value is None else round(float(value), 2)


def _projected_points(player: dict[str, Any], scoring_period: int) -> float | None:
    for stat in player.get("stats", []):
        if (
            stat.get("statSourceId") == PROJECTION_SOURCE_ID
            and stat.get("scoringPeriodId") == scoring_period
        ):
            return _round(stat.get("appliedTotal"))
    return None


def _shape_matchup_player(entry: dict[str, Any], scoring_period: int) -> dict[str, Any]:
    pool_entry = entry.get("playerPoolEntry", {})
    row = _shape_player(entry)
    points = pool_entry.get("appliedStatTotal")
    row["points"] = _round(points) if points is not None else 0.0
    row["projected"] = _projected_points(pool_entry.get("player", {}), scoring_period)
    return row


def _side_score(side: dict[str, Any]) -> float:
    live = side.get("totalPointsLive")
    value = live if live is not None else side.get("totalPoints")
    return _round(value) if value is not None else 0.0


def _shape_side(side: dict[str, Any], league: dict[str, Any]) -> dict[str, Any]:
    team_id = side.get("teamId")
    team = _find_team(league, team_id) or {}
    projected = side.get("totalProjectedPointsLive")
    if projected is None:
        projected = side.get("totalProjectedPoints")
    entries = sorted(
        side.get("rosterForCurrentScoringPeriod", {}).get("entries", []), key=_slot_sort_key
    )
    scoring_period = league.get("scoringPeriodId", -1)
    return {
        "team_id": team_id,
        "name": team.get("name"),
        "abbrev": team.get("abbrev"),
        "score": _side_score(side),
        "projected": _round(projected),
        "win_probability": side.get("winProbability"),
        "roster": [_shape_matchup_player(e, scoring_period) for e in entries],
    }


def _matchup_status(game: dict[str, Any]) -> str:
    if game.get("winner") in ("HOME", "AWAY", "TIE"):
        return "FINAL"
    if _side_score(game.get("home", {})) > 0 or _side_score(game.get("away", {})) > 0:
        return "IN_PROGRESS"
    return "UPCOMING"


def shape_matchup(game: dict[str, Any], league: dict[str, Any], my_team_id: int) -> dict[str, Any]:
    """Shape one schedule game from the perspective of ``my_team_id``.

    Side-level ``score``/``projected`` are ESPN's matchup-period totals; roster
    rows come from ``rosterForCurrentScoringPeriod`` and cover the current NFL
    week only (identical for 1-week matchup periods, which is all we support).
    """
    home, away = game.get("home", {}), game.get("away", {})
    is_home = home.get("teamId") == my_team_id
    mine, theirs = (home, away) if is_home else (away, home)
    return {
        "week": game.get("matchupPeriodId"),
        "status": _matchup_status(game),
        "is_home": is_home,
        "my_team": _shape_side(mine, league),
        "opponent": _shape_side(theirs, league),
    }
