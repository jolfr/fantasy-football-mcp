"""Pure functions that shape ESPN league JSON into tool output."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fantasy_mcp import ids
from fantasy_mcp.config import Settings
from fantasy_mcp.espn import EspnError
from fantasy_mcp.lineup import NON_STARTING_SLOTS, optimal_lineup
from fantasy_mcp.schedules import game_context, iso_utc
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


def shape_team(
    team: dict[str, Any],
    *,
    league: dict[str, Any] | None = None,
    scoring_period: int | None = None,
    season: int | None = None,
) -> dict[str, Any]:
    """Shape one team. With ``league`` given, adds ``owner`` and per-row ``projected``."""
    overall = team.get("record", {}).get("overall", {})
    entries = sorted(team.get("roster", {}).get("entries", []), key=_slot_sort_key)
    roster = [_shape_player(e) for e in entries]
    if league is not None:
        for row, entry in zip(roster, entries):
            player = (entry.get("playerPoolEntry") or {}).get("player") or {}
            row["projected"] = (
                _stat(player, period=scoring_period, source=PROJECTION_SOURCE_ID, season=season)
                if scoring_period is not None and season is not None
                else None
            )
    shaped = {
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
        "roster": roster,
    }
    if league is not None:
        shaped["owner"] = _owner_name(league, team)
    return shaped


def _describe_team(team: dict[str, Any]) -> str:
    return f"{team.get('name')} ({team.get('abbrev')}, id {team.get('id')})"


def find_team_by_name(league: dict[str, Any], query: str) -> dict[str, Any]:
    """Resolve a team by abbreviation (exact), name (exact), then name-contains; else raise."""
    teams = league.get("teams") or []
    q = query.strip().casefold()
    for matcher in (
        lambda t: (t.get("abbrev") or "").casefold() == q,
        lambda t: (t.get("name") or "").casefold() == q,
        lambda t: q in (t.get("name") or "").casefold(),
    ):
        hits = [t for t in teams if matcher(t)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            listed = "; ".join(_describe_team(t) for t in hits)
            raise EspnError(f"{query!r} matches {len(hits)} teams: {listed}. Pass the team id.")
    listed = "; ".join(_describe_team(t) for t in teams)
    raise EspnError(f"No team matches {query!r}. Teams: {listed}.")


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
    roster = [_shape_matchup_player(e, scoring_period, season) for e in entries]
    projected_source = "espn" if projected is not None else None
    if projected is None:
        # Future weeks: ESPN has no team projection yet, but per-player ones exist.
        starter_projections = [
            r["projected"]
            for r, e in zip(roster, entries)
            if e.get("lineupSlotId") not in NON_STARTING_SLOTS and r["projected"] is not None
        ]
        if starter_projections:
            projected, projected_source = sum(starter_projections), "sum_of_starters"
    return {
        "team_id": team_id,
        "name": team.get("name"),
        "abbrev": team.get("abbrev"),
        "score": _side_score(side),
        "projected": _round(projected),
        "projected_source": projected_source,
        "win_probability": side.get("winProbability"),
        "roster": roster,
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


def _scoring_summary(rules: dict[str, int | float], scoring_type: str | None = None) -> str:
    parts: list[str] = []
    if scoring_type and "POINTS" not in scoring_type:
        parts.append(f"{scoring_type} (not points-based; rules below may not apply)")
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
            "summary": _scoring_summary(rules, scoring.get("scoringType")),
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


def _projection_for(player: dict[str, Any], week: int, season: int) -> float | None:
    return _stat(player, period=week, source=PROJECTION_SOURCE_ID, season=season)


def _lineup_row(slot_id: int, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot": ids.name(ids.LINEUP_SLOTS, slot_id),
        "player_id": row["player_id"],
        "name": row["name"],
        "projected": row["projected"],
    }


def shape_projections(
    week: int,
    roster_entries: list[dict[str, Any]],
    projections_players: list[dict[str, Any]],
    schedules: dict[str, Any],
    slot_counts: dict[int, int],
    *,
    season: int,
    current_week: int | None = None,
) -> dict[str, Any]:
    """Weekly projections for a roster plus a suggested optimal lineup and the changes to reach it."""
    by_id = {p.get("id"): p.get("player") or {} for p in projections_players or []}

    rows: list[dict[str, Any]] = []
    for entry in roster_entries or []:
        base = _shape_player(entry)
        player = by_id.get(base["player_id"]) or (entry.get("playerPoolEntry") or {}).get("player") or {}
        pro_team_id = player.get("proTeamId")
        context = game_context(schedules, pro_team_id, week)
        rows.append(
            {
                **{k: base[k] for k in ("player_id", "name", "position", "pro_team", "injury_status", "slot")},
                "opponent": context["opponent"],
                "kickoff": context["kickoff"],
                "projected": _projection_for(player, week, season),
                "_slot_id": entry.get("lineupSlotId", 99),
                "_eligible": player.get("eligibleSlots") or [],
            }
        )

    starters = [r for r in rows if r["_slot_id"] not in NON_STARTING_SLOTS]
    others = [r for r in rows if r["_slot_id"] in NON_STARTING_SLOTS]
    starters.sort(key=lambda r: r["_slot_id"])
    others.sort(key=lambda r: -(r["projected"] or 0))
    ordered = starters + others

    lineup_input = [
        {"player_id": r["player_id"], "name": r["name"], "projected": r["projected"],
         "eligible_slots": r["_eligible"], "slot_id": r["_slot_id"],
         "injury_status": r["injury_status"]}
        for r in ordered
    ]
    assigned = optimal_lineup(lineup_input, slot_counts or {})
    suggested = [_lineup_row(slot, row) for slot in sorted(assigned) for row in assigned[slot]]

    current_ids = {r["player_id"] for r in starters}
    suggested_ids = {r["player_id"] for r in suggested}
    current_total = round(sum(r["projected"] or 0 for r in starters), 2)
    suggested_total = round(sum(r["projected"] or 0 for r in suggested), 2)
    sit = [
        {"slot": r["slot"], "player_id": r["player_id"], "name": r["name"], "projected": r["projected"]}
        for r in starters if r["player_id"] not in suggested_ids
    ]
    start = [r for r in suggested if r["player_id"] not in current_ids]

    public_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in ordered]
    return {
        "week": week,
        "current_week": current_week,
        "players": public_rows,
        "current_total": current_total,
        "suggested_lineup": suggested,
        "suggested_total": suggested_total,
        "changes": {"start": start, "sit": sit, "gain": round(suggested_total - current_total, 2)},
    }


def _owner_name(league: dict[str, Any], team: dict[str, Any]) -> str | None:
    owners = team.get("owners") or []
    if not owners:
        return None
    swid = str(owners[0]).lower()
    member = next((m for m in league.get("members") or [] if str(m.get("id", "")).lower() == swid), None)
    if not member:
        return None
    first, last = (member.get("firstName") or "").strip(), (member.get("lastName") or "").strip()
    if first and last:
        return f"{first} {last}"
    return first or member.get("displayName") or None


def _streak(overall: dict[str, Any]) -> str | None:
    kind, length = overall.get("streakType"), overall.get("streakLength") or 0
    if kind not in ("WIN", "LOSS") or not length:
        return None
    return f"{'W' if kind == 'WIN' else 'L'}{int(length)}"


def _standings_row(league: dict[str, Any], team: dict[str, Any], my_team_id: int | None) -> dict[str, Any]:
    overall = (team.get("record") or {}).get("overall") or {}
    counter = team.get("transactionCounter") or {}
    clinch = team.get("playoffClinchType")
    return {
        "rank": team.get("playoffSeed") or 0,  # re-numbered after sorting
        "team_id": team.get("id"),
        "name": team.get("name"),
        "abbrev": team.get("abbrev"),
        "owner": _owner_name(league, team),
        "is_me": team.get("id") == my_team_id,
        "record": {
            "wins": overall.get("wins", 0),
            "losses": overall.get("losses", 0),
            "ties": overall.get("ties", 0),
        },
        "points_for": _round(overall.get("pointsFor", 0.0)),
        "points_against": _round(overall.get("pointsAgainst", 0.0)),
        "streak": _streak(overall),
        "games_back": _round(overall.get("gamesBack", 0.0)),
        "projected_rank": team.get("currentProjectedRank") or None,
        "waiver_priority": team.get("waiverRank") or None,
        "transactions": {
            "acquisitions": counter.get("acquisitions", 0),
            "drops": counter.get("drops", 0),
            "trades": counter.get("trades", 0),
            "faab_spent": counter.get("acquisitionBudgetSpent", 0),
        },
        "clinched": clinch if clinch and clinch != "NONE" else None,
    }


def shape_standings(league: dict[str, Any], my_team_id: int | None) -> dict[str, Any]:
    """League standings ordered by playoff seed (then record), with the user's team flagged."""
    rows = [_standings_row(league, t, my_team_id) for t in league.get("teams") or []]
    rows.sort(
        key=lambda r: (
            r["rank"] == 0,  # seeded teams first
            r["rank"],
            -r["record"]["wins"],
            -(r["points_for"] or 0),
        )
    )
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    schedule = (league.get("settings") or {}).get("scheduleSettings") or {}
    return {
        "season": league.get("seasonId"),
        "week": (league.get("status") or {}).get("currentMatchupPeriod"),
        "playoff_teams": schedule.get("playoffTeamCount"),
        "playoff_seeding": schedule.get("playoffSeedingRule"),
        "teams": rows,
    }


GAMES_PLAYED_STAT = "210"  # raw stat present only on weeks the player actually played


def _weekly_actual_entries(player: dict[str, Any], season: int) -> list[dict[str, Any]]:
    entries = [
        s
        for s in player.get("stats") or []
        if s.get("seasonId") == season
        and s.get("statSourceId") == ACTUAL_SOURCE_ID
        and (s.get("scoringPeriodId") or 0) > 0
    ]
    return sorted(entries, key=lambda s: -(s.get("scoringPeriodId") or 0))


def _weekly_actuals(player: dict[str, Any], season: int) -> list[tuple[int, float]]:
    """(week, points) for this season's weekly actual entries, newest first."""
    return [
        (int(s.get("scoringPeriodId") or 0), float(s.get("appliedTotal") or 0.0))
        for s in _weekly_actual_entries(player, season)
    ]


def _games_played(player: dict[str, Any], season: int) -> int:
    """Weeks with a games-played stat line; ESPN also emits 0-point entries for weeks not played."""
    return sum(
        1 for s in _weekly_actual_entries(player, season) if (s.get("stats") or {}).get(GAMES_PLAYED_STAT)
    )


def _season_line(player: dict[str, Any], season: int) -> tuple[float | None, int, float | None]:
    points = _stat(player, period=SEASON_PERIOD, source=ACTUAL_SOURCE_ID, season=season)
    games = _games_played(player, season)
    avg = _round(points / games) if points is not None and games else None
    return points, games, avg


def shape_comparison(
    entries: list[dict[str, Any]], league: dict[str, Any], week: int, schedules: dict[str, Any]
) -> list[dict[str, Any]]:
    """Compact side-by-side rows for compare_players; entries with an ``error`` key pass through."""

    season = league.get("seasonId", -1)
    rows: list[dict[str, Any]] = []
    for entry in entries:
        if "error" in entry:
            rows.append({"player_id": entry.get("player_id", entry.get("id")), "error": entry["error"]})
            continue
        player = entry.get("player") or {}
        ownership = player.get("ownership") or {}
        player_id = entry.get("id", player.get("id"))
        position = ids.name(ids.POSITIONS, player.get("defaultPositionId", -1))
        pro_team = ids.name(ids.PRO_TEAMS, player.get("proTeamId", -1))
        team = _find_team(league, entry.get("onTeamId")) if entry.get("onTeamId") else None
        rank = ((entry.get("ratings") or {}).get("0") or {}).get("positionalRanking") or None
        context = game_context(schedules, player.get("proTeamId"), week)
        points, games, avg = _season_line(player, season)
        last_points, last_games, last_avg = _season_line(player, season - 1)
        rows.append(
            {
                "player_id": player_id,
                "name": player.get("fullName"),
                "position": position,
                "pro_team": pro_team,
                "injury_status": player.get("injuryStatus"),
                "league_status": entry.get("status"),
                "owned_by": team.get("name") if team else None,
                "headshot_url": headshot_url(player_id, position, pro_team),
                "week": {
                    "projected": _stat(player, period=week, source=PROJECTION_SOURCE_ID, season=season),
                    "opponent": context["opponent"],
                    "kickoff": context["kickoff"],
                },
                "season": {
                    "projected": _stat(player, period=SEASON_PERIOD, source=PROJECTION_SOURCE_ID, season=season),
                    "points": points,
                    "positional_rank": rank,
                    "games": games,
                    "avg": avg,
                },
                "last_3": [_round(p) for _, p in _weekly_actuals(player, season)[:3]],
                "last_season": (
                    {"points": last_points, "games": last_games, "avg": last_avg}
                    if last_points is not None
                    else None
                ),
                "percent_owned": _round(ownership.get("percentOwned"), ndigits=1),
                "percent_change": _round(ownership.get("percentChange"), ndigits=1),
            }
        )
    return rows


TRANSACTION_TYPE_LABELS = {
    "WAIVER": "Waiver claim",
    "FREEAGENT": "Free agent move",
    "DRAFT": "Draft pick",
}

# ESPN's own `status` on a trade transaction is "EXECUTED" for every TRADE_* type
# except the one that actually completed it (TRADE_ACCEPT, where "EXECUTED" is
# already the right word) -- so the real outcome has to come from the type suffix.
TRADE_STATUS_BY_TYPE = {
    "TRADE_DECLINE": "DECLINED",
    "TRADE_VETO": "VETOED",
    "TRADE_PROPOSAL": "PROPOSED",
}


def _normalize_transaction_type_status(
    espn_type: str | None, raw_status: str | None, items: list[dict[str, Any]]
) -> tuple[str | None, str | None]:
    if espn_type and espn_type.startswith("TRADE_"):
        return "TRADE", TRADE_STATUS_BY_TYPE.get(espn_type, raw_status)
    if espn_type == "ROSTER":
        only_lineup = bool(items) and all(i.get("type") == "LINEUP" for i in items)
        return ("LINEUP" if only_lineup else "FREEAGENT"), raw_status
    return espn_type, raw_status


def _transaction_team_name(league: dict[str, Any], team_id: Any) -> str | None:
    if not team_id:
        return None
    team = _find_team(league, team_id)
    return team.get("name") if team else None


def _transaction_slot_name(slot_id: Any) -> str | None:
    if slot_id is None or slot_id == -1:
        return None
    return ids.name(ids.LINEUP_SLOTS, slot_id)


def _shape_transaction_item(
    item: dict[str, Any], league: dict[str, Any], index_by_id: dict[Any, dict[str, Any]]
) -> dict[str, Any]:
    player_id = item.get("playerId")
    player = index_by_id.get(player_id) if player_id is not None else None
    if player is not None:
        name = player.get("fullName")
        position = ids.name(ids.POSITIONS, player.get("defaultPositionId", -1))
        pro_team = ids.name(ids.PRO_TEAMS, player.get("proTeamId", -1))
    else:
        name, position, pro_team = None, "UNKNOWN_-1", "UNKNOWN_-1"
    return {
        "action": item.get("type"),
        "player_id": player_id,
        "name": name,
        "position": position,
        "pro_team": pro_team,
        "from_team": _transaction_team_name(league, item.get("fromTeamId")),
        "to_team": _transaction_team_name(league, item.get("toTeamId")),
        "from_slot": _transaction_slot_name(item.get("fromLineupSlotId")),
        "to_slot": _transaction_slot_name(item.get("toLineupSlotId")),
    }


def _item_display_name(item: dict[str, Any]) -> str:
    """Item's player name, falling back to ``player <id>`` when unresolved (unknown id)."""
    return item["name"] or f"player {item['player_id']}"


def _trade_summary(status: str | None, items: list[dict[str, Any]]) -> str:
    sides: dict[str, list[str]] = {}
    order: list[str] = []
    for item in items:
        sender = item["from_team"] or "Unknown"
        if sender not in sides:
            sides[sender] = []
            order.append(sender)
        sides[sender].append(_item_display_name(item))
    body = "; ".join(f"{team} sends {', '.join(sides[team])}" for team in order)
    status_word = (status or "").lower()
    return f"Trade {status_word}: {body}" if body else f"Trade {status_word}"


def _lineup_summary(items: list[dict[str, Any]]) -> str:
    moves = ", ".join(f"{_item_display_name(i)} to {i['to_slot']}" for i in items)
    return f"Lineup change: {moves}" if moves else "Lineup change"


def _transaction_summary(
    norm_type: str | None, status: str | None, bid: int, items: list[dict[str, Any]]
) -> str:
    if norm_type == "LINEUP":
        return _lineup_summary(items)
    if norm_type == "TRADE":
        return _trade_summary(status, items)
    label = TRANSACTION_TYPE_LABELS.get(norm_type, norm_type.title() if norm_type else "Transaction")
    status_word = (status or "").lower()
    bid_part = f" (${bid})" if bid else ""
    moves = [f"add {_item_display_name(i)}" for i in items if i["action"] == "ADD"]
    moves += [f"drop {_item_display_name(i)}" for i in items if i["action"] == "DROP"]
    body = f": {', '.join(moves)}" if moves else ""
    return f"{label} {status_word}{bid_part}{body}".strip()


def _shape_transaction(
    t: dict[str, Any], league: dict[str, Any], index_by_id: dict[Any, dict[str, Any]]
) -> dict[str, Any]:
    espn_type = t.get("type")
    raw_items = t.get("items") or []
    norm_type, status = _normalize_transaction_type_status(espn_type, t.get("status"), raw_items)
    items = [_shape_transaction_item(i, league, index_by_id) for i in raw_items]
    bid = t.get("bidAmount") or 0
    return {
        "id": t.get("id"),
        "type": norm_type,
        "espn_type": espn_type,
        "status": status,
        "week": t.get("scoringPeriodId"),
        "team": {"team_id": t.get("teamId"), "name": _transaction_team_name(league, t.get("teamId"))},
        "proposed": iso_utc(t.get("proposedDate")),
        "processed": iso_utc(t.get("processDate")),
        "bid": bid,
        "items": items,
        "summary": _transaction_summary(norm_type, status, bid, items),
    }


def _transaction_matches_team(t: dict[str, Any], team_id: int) -> bool:
    if t.get("teamId") == team_id:
        return True
    return any(i.get("fromTeamId") == team_id or i.get("toTeamId") == team_id for i in t.get("items") or [])


def _is_lineup_only(t: dict[str, Any]) -> bool:
    items = t.get("items") or []
    return bool(items) and all(i.get("type") == "LINEUP" for i in items)


def shape_transactions(
    league: dict[str, Any],
    index_by_id: dict[Any, dict[str, Any]],
    *,
    team_id: int | None = None,
    limit: int = 25,
    include_lineup_moves: bool = False,
) -> dict[str, Any]:
    """Shape ``mTransactions2`` (+ ``mTeam``) into the transaction log, newest first."""
    transactions = league.get("transactions") or []
    if team_id is not None:
        transactions = [t for t in transactions if _transaction_matches_team(t, team_id)]
    if not include_lineup_moves:
        transactions = [t for t in transactions if not _is_lineup_only(t)]
    transactions = sorted(transactions, key=lambda t: t.get("proposedDate") or 0, reverse=True)[:limit]
    return {
        "week": league.get("scoringPeriodId"),
        "transactions": [_shape_transaction(t, league, index_by_id) for t in transactions],
    }
