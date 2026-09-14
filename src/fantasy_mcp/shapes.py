"""Pure functions that shape ESPN league JSON into tool output."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fantasy_mcp import ids
from fantasy_mcp.config import Settings
from fantasy_mcp.espn import EspnError
from fantasy_mcp.stats import scoring_name, shape_stat_line

# player.stats[] items are keyed by scoringPeriodId (0 = season total, N = week N)
# and statSourceId (0 = actual, 1 = projected).
SEASON_PERIOD = 0
ACTUAL_SOURCE_ID = 0
PROJECTION_SOURCE_ID = 1

BENCH_SLOT = 20
IR_SLOT = 21

HEADSHOT_URL = (
    "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/{player_id}.png&w=350&h=254"
)
TEAM_LOGO_URL = "https://a.espncdn.com/i/teamlogos/nfl/500/{team}.png"


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
    pool_entry = entry.get("playerPoolEntry") or {}
    player = pool_entry.get("player") or {}
    return {
        "player_id": entry.get("playerId", pool_entry.get("id")),
        "name": player.get("fullName"),
        "position": ids.name(ids.POSITIONS, player.get("defaultPositionId", -1)),
        "slot": ids.name(ids.LINEUP_SLOTS, entry.get("lineupSlotId", -1)),
        "pro_team": ids.name(ids.PRO_TEAMS, player.get("proTeamId", -1)),
        "injury_status": player.get("injuryStatus"),
    }


def _slot_sort_key(entry: dict[str, Any]) -> tuple[int, int]:
    slot = entry.get("lineupSlotId", 99)
    # Starters (anything not bench/IR) first, then bench, then IR.
    bucket = {BENCH_SLOT: 1, IR_SLOT: 2}.get(slot, 0)
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


def _round(value: Any, ndigits: int = 2) -> float | None:
    if value is None:
        return None
    result = round(float(value), ndigits)
    return 0.0 if result == 0 else result  # normalize -0.0


def _stat(player: dict[str, Any], *, period: int, source: int, season: int) -> float | None:
    """appliedTotal of the stats[] item for ``period``/``source``/``season``, rounded.

    ESPN includes prior-season totals under the same period/source keys, so the
    ``seasonId`` must match exactly. Returns None if no such item exists.
    """
    for stat in player.get("stats") or []:
        if (
            stat.get("scoringPeriodId") == period
            and stat.get("statSourceId") == source
            and stat.get("seasonId") == season
        ):
            return _round(stat.get("appliedTotal"))
    return None


def _projected_points(player: dict[str, Any], scoring_period: int, season: int) -> float | None:
    return _stat(player, period=scoring_period, source=PROJECTION_SOURCE_ID, season=season)


def _shape_matchup_player(entry: dict[str, Any], scoring_period: int, season: int) -> dict[str, Any]:
    pool_entry = entry.get("playerPoolEntry", {})
    row = _shape_player(entry)
    points = pool_entry.get("appliedStatTotal")
    row["points"] = _round(points) if points is not None else 0.0
    row["projected"] = _projected_points(pool_entry.get("player", {}), scoring_period, season)
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
    season = league.get("seasonId", -1)  # -1: no stat can match; never guess a year
    return {
        "team_id": team_id,
        "name": team.get("name"),
        "abbrev": team.get("abbrev"),
        "score": _side_score(side),
        "projected": _round(projected),
        "win_probability": side.get("winProbability"),
        "roster": [_shape_matchup_player(e, scoring_period, season) for e in entries],
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


def shape_free_agent(entry: dict[str, Any], scoring_period: int, season: int) -> dict[str, Any]:
    """Shape one kona_player_info players[] entry for the free-agent list."""
    player = entry.get("player") or {}
    ownership = player.get("ownership") or {}
    season_rating = (entry.get("ratings") or {}).get("0") or {}
    return {
        "player_id": entry.get("id"),
        "name": player.get("fullName"),
        "position": ids.name(ids.POSITIONS, player.get("defaultPositionId", -1)),
        "pro_team": ids.name(ids.PRO_TEAMS, player.get("proTeamId", -1)),
        "injury_status": player.get("injuryStatus"),
        "status": entry.get("status"),
        "percent_owned": _round(ownership.get("percentOwned"), ndigits=1),
        "percent_change": _round(ownership.get("percentChange")),
        "season_projected": _stat(
            player, period=SEASON_PERIOD, source=PROJECTION_SOURCE_ID, season=season
        ),
        "season_points": _stat(
            player, period=SEASON_PERIOD, source=ACTUAL_SOURCE_ID, season=season
        ),
        "week_projected": _stat(
            player, period=scoring_period, source=PROJECTION_SOURCE_ID, season=season
        ),
        "week_points": _stat(
            player, period=scoring_period, source=ACTUAL_SOURCE_ID, season=season
        ),
        # ESPN reports 0 for unranked players; surface that as null, not "rank 0".
        "positional_rank": season_rating.get("positionalRanking") or None,
    }


_NON_STARTING_SLOTS = {BENCH_SLOT, IR_SLOT}


def _game_log(player: dict[str, Any], season: int) -> list[dict[str, Any]]:
    seasons = {season, season - 1}
    projections = {
        (s.get("seasonId"), s.get("scoringPeriodId")): _round(s.get("appliedTotal"))
        for s in player.get("stats") or []
        if s.get("statSourceId") == PROJECTION_SOURCE_ID and (s.get("scoringPeriodId") or 0) > 0
    }
    rows = []
    for s in player.get("stats") or []:
        year, week = s.get("seasonId"), s.get("scoringPeriodId") or 0
        if s.get("statSourceId") != ACTUAL_SOURCE_ID or week <= 0 or year not in seasons:
            continue
        rows.append(
            {
                "season": year,
                "week": week,
                "points": _round(s.get("appliedTotal")),
                "projected": projections.get((year, week)),
                "stats": shape_stat_line(s.get("stats")),
            }
        )
    rows.sort(key=lambda r: (r["season"], r["week"]), reverse=True)
    return rows


def headshot_url(player_id: int | None, position: str | None, pro_team: str | None) -> str | None:
    """ESPN CDN image for a player (headshot) or a D/ST (team logo); None if unknown."""
    if position == "D/ST":
        if pro_team and pro_team != "FA" and not pro_team.startswith("UNKNOWN_"):
            return TEAM_LOGO_URL.format(team=pro_team.lower())
        return None
    if player_id is None:
        return None
    return HEADSHOT_URL.format(player_id=player_id)


def shape_player_card(entry: dict[str, Any], league: dict[str, Any]) -> dict[str, Any]:
    """Shape one kona_playercard players[] entry into a full player profile."""
    season = league.get("seasonId", -1)
    player = entry.get("player") or {}
    ownership = player.get("ownership") or {}
    rank = ((entry.get("ratings") or {}).get("0") or {}).get("positionalRanking") or None
    team = _find_team(league, entry.get("onTeamId")) if entry.get("onTeamId") else None
    last_points = _stat(player, period=SEASON_PERIOD, source=ACTUAL_SOURCE_ID, season=season - 1)
    player_id = entry.get("id", player.get("id"))
    position = ids.name(ids.POSITIONS, player.get("defaultPositionId", -1))
    pro_team = ids.name(ids.PRO_TEAMS, player.get("proTeamId", -1))
    return {
        "player_id": player_id,
        "headshot_url": headshot_url(player_id, position, pro_team),
        "name": player.get("fullName"),
        "position": position,
        "pro_team": pro_team,
        "injury_status": player.get("injuryStatus"),
        "injured": player.get("injured"),
        "eligible_slots": [
            ids.name(ids.LINEUP_SLOTS, slot)
            for slot in player.get("eligibleSlots") or []
            if slot not in _NON_STARTING_SLOTS
        ],
        "league_status": entry.get("status"),
        "owned_by": {"team_id": team.get("id"), "name": team.get("name")} if team else None,
        "ownership": {
            "percent_owned": _round(ownership.get("percentOwned"), ndigits=1),
            "percent_started": _round(ownership.get("percentStarted"), ndigits=1),
            "percent_change": _round(ownership.get("percentChange"), ndigits=1),
            "adp": _round(ownership.get("averageDraftPosition"), ndigits=1),
        },
        "season": {
            "year": season,
            "projected": _stat(player, period=SEASON_PERIOD, source=PROJECTION_SOURCE_ID, season=season),
            "points": _stat(player, period=SEASON_PERIOD, source=ACTUAL_SOURCE_ID, season=season),
            "positional_rank": rank,
        },
        "last_season": {"year": season - 1, "points": last_points} if last_points is not None else None,
        "outlook": player.get("seasonOutlook") or None,
        "game_log": _game_log(player, season),
    }


DST_POSITION_ID = 16


def _num(value: Any) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _scoring_rules(items: list[dict[str, Any]]) -> dict[str, int | float]:
    rules: dict[str, int | float] = {}
    for item in items or []:
        points = item.get("points") or 0
        if not points:
            points = (item.get("pointsOverrides") or {}).get(str(DST_POSITION_ID)) or 0
        if points and item.get("statId") is not None:
            rules[scoring_name(int(item["statId"]))] = _num(points)
    return rules


def _per_point(points: int | float) -> int | float:
    return _num(round(1 / points)) if points else 0


def _scoring_summary(rules: dict[str, int | float]) -> str:
    parts: list[str] = []
    ppr = rules.get("receptions", 0)
    parts.append(
        "Full PPR" if ppr == 1 else "Half PPR" if ppr == 0.5 else f"{ppr} PPR" if ppr else "Standard (no PPR)"
    )
    if rules.get("pass_yds"):
        parts.append(f"{_per_point(rules['pass_yds'])} pass yds/pt")
    rush_y, rec_y = rules.get("rush_yds"), rules.get("rec_yds")
    if rush_y and rush_y == rec_y:
        parts.append(f"{_per_point(rush_y)} rush/rec yds/pt")
    else:
        if rush_y:
            parts.append(f"{_per_point(rush_y)} rush yds/pt")
        if rec_y:
            parts.append(f"{_per_point(rec_y)} rec yds/pt")
    if rules.get("pass_td"):
        parts.append(f"{rules['pass_td']}-pt pass TD")
    rush_td, rec_td = rules.get("rush_td"), rules.get("rec_td")
    if rush_td and rush_td == rec_td:
        parts.append(f"{rush_td}-pt rush/rec TD")
    else:
        if rush_td:
            parts.append(f"{rush_td}-pt rush TD")
        if rec_td:
            parts.append(f"{rec_td}-pt rec TD")
    if rules.get("pass_int"):
        parts.append(f"{rules['pass_int']} INT")
    if rules.get("fumbles_lost"):
        parts.append(f"{rules['fumbles_lost']} fumble lost")
    return " · ".join(parts)


def _epoch_ms_date(value: Any) -> str | None:
    if not value:
        return None
    return dt.datetime.fromtimestamp(int(value) / 1000, dt.timezone.utc).date().isoformat()


def _unlimited_to_none(value: Any) -> Any:
    return None if value is None or value == -1 else value


def shape_league_settings(league: dict[str, Any]) -> dict[str, Any]:
    """Shape an ``mSettings`` payload into scoring, roster, schedule, waiver, and trade rules."""
    settings = league.get("settings") or {}
    roster = settings.get("rosterSettings") or {}
    scoring = settings.get("scoringSettings") or {}
    schedule = settings.get("scheduleSettings") or {}
    waivers = settings.get("acquisitionSettings") or {}
    trades = settings.get("tradeSettings") or {}
    status = league.get("status") or {}

    rules = _scoring_rules(scoring.get("scoringItems") or [])
    lineup = {
        ids.name(ids.LINEUP_SLOTS, int(slot)): count
        for slot, count in sorted((roster.get("lineupSlotCounts") or {}).items(), key=lambda kv: int(kv[0]))
        if count
    }
    limits = {
        ids.name(ids.POSITIONS, int(pos)): limit
        for pos, limit in sorted((roster.get("positionLimits") or {}).items(), key=lambda kv: int(kv[0]))
        if limit is not None and limit > 0
    }
    return {
        "league_name": settings.get("name"),
        "size": settings.get("size"),
        "is_public": settings.get("isPublic"),
        "scoring": {
            "type": scoring.get("scoringType"),
            "ppr": rules.get("receptions", 0),
            "rules": rules,
            "summary": _scoring_summary(rules),
        },
        "roster": {
            "lineup": lineup,
            "position_limits": limits,
            "move_limit": _unlimited_to_none(roster.get("moveLimit")),
            "lineup_lock": roster.get("lineupLocktimeType"),
        },
        "schedule": {
            "regular_season_weeks": schedule.get("matchupPeriodCount"),
            "matchup_weeks_per_period": schedule.get("matchupPeriodLength"),
            "playoff_teams": schedule.get("playoffTeamCount"),
            "playoff_seeding": schedule.get("playoffSeedingRule"),
            "current_week": status.get("currentMatchupPeriod"),
            "final_week": status.get("finalScoringPeriod"),
        },
        "waivers": {
            "type": waivers.get("acquisitionType"),
            "budget": waivers.get("acquisitionBudget"),
            "min_bid": waivers.get("minimumBid"),
            "waiver_hours": waivers.get("waiverHours"),
            "order_resets": waivers.get("waiverOrderReset"),
            "process_days": waivers.get("waiverProcessDays") or [],
        },
        "trades": {
            "deadline": _epoch_ms_date(trades.get("deadlineDate")),
            "review_hours": trades.get("revisionHours"),
            "veto_votes_required": trades.get("vetoVotesRequired"),
        },
    }
