import pytest

from fantasy_mcp import shapes
from fantasy_mcp.espn import EspnError


def test_shape_team_orders_starters_first_and_maps_ids(league_json):
    team = league_json["teams"][0]
    shaped = shapes.shape_team(team)

    assert shaped["team_id"] == 3
    assert shaped["name"] == "My Squad"
    assert shaped["abbrev"] == "MYS"
    assert shaped["record"] == {"wins": 1, "losses": 0, "ties": 0}
    assert shaped["points_for"] == 128.4
    assert shaped["points_against"] == 101.2

    names = [p["name"] for p in shaped["roster"]]
    assert names == ["Josh Allen", "Flex Player", "Bench Guy"]

    allen = shaped["roster"][0]
    assert allen == {
        "player_id": 102,
        "name": "Josh Allen",
        "position": "QB",
        "slot": "QB",
        "pro_team": "BUF",
        "injury_status": "ACTIVE",
    }
    assert shaped["roster"][1]["pro_team"] == "UNKNOWN_99"
    assert shaped["roster"][2]["slot"] == "BENCH"


def test_shape_team_tolerates_entry_without_player(league_json):
    team = league_json["teams"][0]
    team["roster"]["entries"].append({"lineupSlotId": 21})
    shaped = shapes.shape_team(team)
    ir_row = shaped["roster"][-1]
    assert ir_row["slot"] == "IR"
    assert ir_row["name"] is None
    assert ir_row["position"] == "UNKNOWN_-1"


def test_shape_whoami(league_json, settings):
    out = shapes.shape_whoami(league_json, team_id=3, settings=settings)
    assert out == {
        "league_id": 4242,
        "season": 2026,
        "league_name": "Test League",
        "team_id": 3,
        "team_name": "My Squad",
    }


def test_team_by_id_missing_raises(league_json):
    with pytest.raises(EspnError, match="ESPN_TEAM_ID"):
        shapes.team_by_id(league_json, 42)


def test_find_matchup_returns_game_containing_team(matchup_json):
    game = shapes.find_matchup(matchup_json, team_id=12, period=1)
    assert game["id"] == 6
    assert game["home"]["teamId"] == 12


def test_find_matchup_matches_away_side_too(matchup_json):
    game = shapes.find_matchup(matchup_json, team_id=11, period=1)
    assert game["id"] == 6


def test_find_matchup_bye_week_raises(matchup_json):
    with pytest.raises(EspnError, match="week 2"):
        shapes.find_matchup(matchup_json, team_id=12, period=2)


def test_shape_matchup_full_shape(matchup_json):
    game = matchup_json["schedule"][0]
    out = shapes.shape_matchup(game, matchup_json, my_team_id=12)

    assert out["week"] == 1
    assert out["status"] == "IN_PROGRESS"
    assert out["is_home"] is True

    me = out["my_team"]
    assert {k: me[k] for k in ("team_id", "name", "abbrev", "score", "projected", "win_probability")} == {
        "team_id": 12,
        "name": "My Matchup Team",
        "abbrev": "MMT",
        "score": 73.3,
        "projected": 136.59,
        "win_probability": 0.76,
    }
    # Starters first (by slot id), then bench, then IR — regardless of file order.
    assert [p["name"] for p in me["roster"]] == [
        "Home Starter One",
        "Home Starter NoStats",
        "Home Bench Guy",
        "Home IR Guy",
    ]
    assert me["roster"][0] == {
        "player_id": 202,
        "name": "Home Starter One",
        "position": "RB",
        "slot": "RB",
        "pro_team": "IND",
        "injury_status": "ACTIVE",
        "points": 18.5,
        "projected": 17.77,
    }
    # No stats[] on the player -> projected is None, points still present.
    assert me["roster"][1]["points"] == 7.0
    assert me["roster"][1]["projected"] is None
    assert me["roster"][3]["slot"] == "IR"
    assert me["roster"][3]["projected"] == 9.73

    opp = out["opponent"]
    assert opp["team_id"] == 11
    assert opp["name"] == "Opponent Team"
    assert opp["score"] == 58.52
    assert opp["projected"] == 106.41
    assert opp["win_probability"] == 0.24
    assert [p["name"] for p in opp["roster"]] == [
        "Away Starter One",
        "Away Starter NoStats",
        "Away Bench Guy",
        "Away IR Guy",
    ]
    assert opp["roster"][0]["projected"] == 18.52


def test_shape_matchup_from_away_perspective(matchup_json):
    game = matchup_json["schedule"][0]
    out = shapes.shape_matchup(game, matchup_json, my_team_id=11)
    assert out["is_home"] is False
    assert out["my_team"]["team_id"] == 11
    assert out["opponent"]["team_id"] == 12


def test_shape_matchup_final_status(matchup_json):
    game = matchup_json["schedule"][0]
    game["winner"] = "AWAY"
    out = shapes.shape_matchup(game, matchup_json, my_team_id=12)
    assert out["status"] == "FINAL"


def test_shape_matchup_upcoming_when_no_points(matchup_json):
    game = matchup_json["schedule"][0]
    for side in ("home", "away"):
        game[side]["totalPointsLive"] = 0.0
        game[side]["totalPoints"] = 0.0
    out = shapes.shape_matchup(game, matchup_json, my_team_id=12)
    assert out["status"] == "UPCOMING"


def test_shape_matchup_falls_back_to_total_points_and_null_projection(matchup_json):
    game = matchup_json["schedule"][0]
    for key in ("totalPointsLive", "totalProjectedPoints", "totalProjectedPointsLive", "winProbability"):
        game["home"].pop(key)
    game["home"]["totalPoints"] = 101.234
    out = shapes.shape_matchup(game, matchup_json, my_team_id=12)
    assert out["my_team"]["score"] == 101.23
    assert out["my_team"]["projected"] is None
    assert out["my_team"]["win_probability"] is None


def test_shape_matchup_unknown_opponent_and_missing_roster(matchup_json):
    game = matchup_json["schedule"][0]
    game["away"]["teamId"] = 77
    del game["away"]["rosterForCurrentScoringPeriod"]
    out = shapes.shape_matchup(game, matchup_json, my_team_id=12)
    assert out["opponent"]["team_id"] == 77
    assert out["opponent"]["name"] is None
    assert out["opponent"]["abbrev"] is None
    assert out["opponent"]["roster"] == []


def test_shape_matchup_tolerates_explicit_null_scores(matchup_json):
    game = matchup_json["schedule"][0]
    game["home"]["totalPointsLive"] = None
    game["home"]["totalPoints"] = None
    game["home"]["totalProjectedPointsLive"] = None
    out = shapes.shape_matchup(game, matchup_json, my_team_id=12)
    assert out["my_team"]["score"] == 0.0
    assert out["my_team"]["projected"] == 113.76  # falls back to totalProjectedPoints
    assert out["status"] == "IN_PROGRESS"  # away side still has live points


def test_shape_matchup_player_points_null_becomes_zero(matchup_json):
    game = matchup_json["schedule"][0]
    game["home"]["rosterForCurrentScoringPeriod"]["entries"][1]["playerPoolEntry"]["appliedStatTotal"] = None
    out = shapes.shape_matchup(game, matchup_json, my_team_id=12)
    assert out["my_team"]["roster"][0]["points"] == 0.0


def test_shape_free_agent_full_entry(free_agents_json):
    entry = free_agents_json["players"][0]
    out = shapes.shape_free_agent(entry, scoring_period=1, season=2026)
    assert out == {
        "player_id": 301,
        "name": "Waiver Back",
        "position": "RB",
        "pro_team": "SF",
        "injury_status": "ACTIVE",
        "status": "WAIVERS",
        "percent_owned": 15.4,
        "percent_change": -0.03,
        "season_projected": 113.78,
        "season_points": 8.0,
        "week_projected": 4.5,
        "week_points": 8.0,
        "positional_rank": 38,
    }


def test_shape_free_agent_sparse_entry_yields_nulls(free_agents_json):
    entry = free_agents_json["players"][1]
    out = shapes.shape_free_agent(entry, scoring_period=1, season=2026)
    assert out["name"] == "Sparse Receiver"
    assert out["position"] == "WR"
    assert out["pro_team"] == "ARI"
    assert out["injury_status"] == "QUESTIONABLE"
    assert out["status"] == "FREEAGENT"
    for key in (
        "percent_owned",
        "percent_change",
        "season_projected",
        "season_points",
        "week_projected",
        "week_points",
        "positional_rank",
    ):
        assert out[key] is None, key


def test_shape_free_agent_rank_zero_is_null(free_agents_json):
    entry = free_agents_json["players"][0]
    entry["ratings"]["0"]["positionalRanking"] = 0
    out = shapes.shape_free_agent(entry, scoring_period=1, season=2026)
    assert out["positional_rank"] is None


def test_shape_free_agent_tolerates_missing_player():
    out = shapes.shape_free_agent({"status": "FREEAGENT"}, scoring_period=1, season=2026)
    assert out["name"] is None
    assert out["position"] == "UNKNOWN_-1"
    assert out["status"] == "FREEAGENT"
    assert out["season_projected"] is None


def test_shape_player_id_falls_back_to_pool_entry_id():
    entry = {"lineupSlotId": 0, "playerPoolEntry": {"id": 555, "player": {"fullName": "X"}}}
    assert shapes._shape_player(entry)["player_id"] == 555


def test_stat_requires_exact_season_match():
    player = {"stats": [
        {"seasonId": 2025, "scoringPeriodId": 0, "statSourceId": 1, "appliedTotal": 999.0},
        {"scoringPeriodId": 0, "statSourceId": 1, "appliedTotal": 555.0},  # unlabeled: never matches
        {"seasonId": 2026, "scoringPeriodId": 0, "statSourceId": 1, "appliedTotal": 100.0},
    ]}
    assert shapes._stat(player, period=0, source=1, season=2026) == 100.0
    assert shapes._stat(player, period=0, source=1, season=2024) is None
    assert shapes._stat(player, period=0, source=0, season=2026) is None


def test_shape_player_card_full(player_card_json):
    entry = player_card_json["players"][0]
    out = shapes.shape_player_card(entry, player_card_json)

    assert {k: out[k] for k in ("player_id", "name", "position", "pro_team", "injury_status", "injured")} == {
        "player_id": 4242335,
        "name": "Card Back",
        "position": "RB",
        "pro_team": "IND",
        "injury_status": "ACTIVE",
        "injured": False,
    }
    assert out["eligible_slots"] == ["RB", "RB/WR", "FLEX", "OP"]
    assert out["league_status"] == "ONTEAM"
    assert out["owned_by"] == {"team_id": 12, "name": "My Matchup Team"}
    assert out["ownership"] == {
        "percent_owned": 99.9,
        "percent_started": 99.6,
        "percent_change": 0.0,
        "adp": 6.4,
    }
    assert out["season"] == {"year": 2026, "projected": 315.58, "points": 25.1, "positional_rank": 4}
    assert out["last_season"] == {"year": 2025, "points": 362.3}
    assert out["outlook"] == "Placeholder outlook: workhorse back with elite volume."

    log = out["game_log"]
    assert [(g["season"], g["week"]) for g in log] == [(2026, 1), (2025, 18), (2025, 17)]
    assert log[0] == {
        "season": 2026,
        "week": 1,
        "points": 25.1,
        "projected": 17.75,
        "stats": {
            "rush_att": 19,
            "rush_yds": 98,
            "rush_td": 2,
            "rec_yds": 23,
            "receptions": 3,
            "targets": 4,
            "fumbles": 1,
            "fumbles_lost": 1,
            "team_loss": 1,
            "games_played": 1,
        },
    }
    assert log[1]["projected"] is None
    assert log[1]["stats"]["rush_yds"] == 26
    assert "41" not in log[0]["stats"]  # unmapped raw id never leaks
    # 2024 rows (both the season total and the week-17 game) are outside season/season-1.
    assert all(g["season"] in (2026, 2025) for g in log)


def test_round_normalizes_negative_zero():
    assert str(shapes._round(-0.001, 1)) == "0.0"
    assert shapes._round(-0.04) == -0.04


def test_shape_player_card_unknown_owner_team_and_id_fallback(player_card_json):
    entry = player_card_json["players"][0]
    entry["onTeamId"] = 99
    del entry["id"]
    out = shapes.shape_player_card(entry, player_card_json)
    assert out["owned_by"] is None
    assert out["player_id"] == 4242335  # from player.id


def test_shape_player_card_unrostered_and_sparse(player_card_json):
    entry = player_card_json["players"][0]
    entry["onTeamId"] = 0
    entry["status"] = "WAIVERS"
    entry["ratings"]["0"]["positionalRanking"] = 0
    entry["player"]["seasonOutlook"] = ""
    del entry["player"]["ownership"]
    out = shapes.shape_player_card(entry, player_card_json)
    assert out["owned_by"] is None
    assert out["league_status"] == "WAIVERS"
    assert out["season"]["positional_rank"] is None
    assert out["outlook"] is None
    assert out["ownership"] == {
        "percent_owned": None,
        "percent_started": None,
        "percent_change": None,
        "adp": None,
    }


def test_shape_player_card_no_last_season():
    league = {"seasonId": 2026, "scoringPeriodId": 1, "teams": []}
    entry = {"id": 9, "onTeamId": 0, "status": "FREEAGENT", "player": {"fullName": "Rookie", "stats": []}}
    out = shapes.shape_player_card(entry, league)
    assert out["last_season"] is None
    assert out["season"] == {"year": 2026, "projected": None, "points": None, "positional_rank": None}
    assert out["game_log"] == []
    assert out["eligible_slots"] == []


def test_headshot_url_for_player_and_dst():
    assert shapes.headshot_url(4242335, "RB", "IND") == (
        "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4242335.png&w=350&h=254"
    )
    assert shapes.headshot_url(-16033, "D/ST", "BAL") == "https://a.espncdn.com/i/teamlogos/nfl/500/bal.png"


def test_headshot_url_missing_cases():
    assert shapes.headshot_url(-1, "D/ST", "UNKNOWN_99") is None
    assert shapes.headshot_url(-1, "D/ST", "FA") is None
    assert shapes.headshot_url(None, "WR", "ARI") is None


def test_shape_player_card_includes_headshot_url(player_card_json):
    out = shapes.shape_player_card(player_card_json["players"][0], player_card_json)
    assert out["headshot_url"].endswith("/4242335.png&w=350&h=254")
    assert list(out)[:2] == ["player_id", "headshot_url"]


def test_shape_league_settings_from_fixture(league_settings_json):
    out = shapes.shape_league_settings(league_settings_json)
    assert out["league_name"] == "Test League"
    assert out["size"] == 12
    assert out["is_public"] is False

    scoring = out["scoring"]
    assert scoring["type"] == "H2H_POINTS"
    assert scoring["ppr"] == 1
    rules = scoring["rules"]
    assert rules["pass_yds"] == 0.04 and rules["pass_td"] == 4 and rules["pass_int"] == -2
    assert rules["rush_yds"] == 0.1 and rules["rec_yds"] == 0.1 and rules["receptions"] == 1
    assert rules["fg_made_50_plus"] == 5 and rules["fg_missed"] == -1
    assert rules["dst_sacks"] == 1 and rules["dst_int"] == 2          # from pointsOverrides["16"]
    assert rules["dst_yards_allowed_200_299"] == 2 and rules["dst_yards_allowed_550_plus"] == -7
    assert rules["stat_63"] == 6                                       # unmapped id kept honestly
    assert "team_win" not in rules                                     # zero-point items dropped
    assert scoring["summary"] == (
        "Full PPR · 25 pass yds/pt · 10 rush/rec yds/pt · 4-pt pass TD · 6-pt rush/rec TD · -2 INT · -2 fumble lost"
    )

    roster = out["roster"]
    assert roster["lineup"] == {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "D/ST": 1, "K": 1, "BENCH": 7, "IR": 1, "FLEX": 1}
    assert list(roster["lineup"]) == ["QB", "RB", "WR", "TE", "D/ST", "K", "BENCH", "IR", "FLEX"]  # slot-id order
    assert roster["position_limits"] == {"QB": 4, "RB": 8, "WR": 8, "TE": 3, "K": 3, "D/ST": 3}
    assert roster["move_limit"] is None
    assert roster["lineup_lock"] == "INDIVIDUAL_GAME"

    assert out["schedule"] == {
        "regular_season_weeks": 14, "matchup_weeks_per_period": 1, "playoff_teams": 6,
        "playoff_seeding": "TOTAL_POINTS_SCORED", "current_week": 1, "final_week": 17,
    }
    assert out["waivers"] == {
        "type": "WAIVERS_TRADITIONAL", "budget": 100, "min_bid": 1, "waiver_hours": 24,
        "order_resets": True,
        "process_days": ["MONDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"],
    }
    assert out["trades"] == {"deadline": "2026-12-02", "review_hours": 24, "veto_votes_required": 5}


def test_shape_league_settings_sparse():
    out = shapes.shape_league_settings({})
    assert out["league_name"] is None and out["size"] is None
    assert out["scoring"] == {"type": None, "ppr": 0, "rules": {}, "summary": "Standard (no PPR)"}
    assert out["roster"] == {"lineup": {}, "position_limits": {}, "move_limit": None, "lineup_lock": None}
    assert out["trades"]["deadline"] is None


def test_scoring_summary_half_ppr_and_split_rules():
    league = {"settings": {"scoringSettings": {"scoringItems": [
        {"statId": 53, "points": 0.5}, {"statId": 24, "points": 0.1}, {"statId": 42, "points": 0.2},
        {"statId": 25, "points": 6}, {"statId": 43, "points": 4}, {"statId": 20, "points": -1},
    ]}}}
    summary = shapes.shape_league_settings(league)["scoring"]["summary"]
    assert summary == "Half PPR · 10 rush yds/pt · 5 rec yds/pt · 6-pt rush TD · 4-pt rec TD · -1 INT"


def test_scoring_summary_flags_non_points_leagues():
    league = {"settings": {"scoringSettings": {"scoringType": "H2H_CATEGORY", "scoringItems": []}}}
    summary = shapes.shape_league_settings(league)["scoring"]["summary"]
    assert summary.startswith("H2H_CATEGORY (not points-based")


def _proj_args(roster_settings_json, projections_json, pro_schedules_json):
    team = roster_settings_json["teams"][0]
    counts = {int(k): v for k, v in roster_settings_json["settings"]["rosterSettings"]["lineupSlotCounts"].items()}
    return 2, team["roster"]["entries"], projections_json["players"], pro_schedules_json, counts


def test_shape_projections_rows_and_lineup(roster_settings_json, projections_json, pro_schedules_json):
    out = shapes.shape_projections(*_proj_args(roster_settings_json, projections_json, pro_schedules_json), season=2026, current_week=1)
    assert out["week"] == 2 and out["current_week"] == 1
    names = [p["name"] for p in out["players"]]
    assert names == ["QB One", "RB One", "WR One", "WR Two", "TE One", "Def One", "Kicker One", "WR Bench"]
    rb = out["players"][1]
    assert rb == {
        "player_id": 4242335, "name": "RB One", "position": "RB", "pro_team": "IND",
        "injury_status": "ACTIVE", "slot": "RB", "opponent": "@KC",
        "kickoff": "2026-09-21T00:20:00Z", "projected": 17.68,
    }
    assert out["players"][5]["opponent"] == "vs NO"
    assert out["current_total"] == 92.76
    assert out["suggested_total"] == 102.78
    assert [(r["slot"], r["name"]) for r in out["suggested_lineup"]] == [
        ("QB", "QB One"), ("RB", "RB One"), ("WR", "WR One"), ("WR", "WR Two"), ("TE", "TE One"),
        ("D/ST", "Def One"), ("K", "Kicker One"), ("FLEX", "WR Bench"),
    ]
    assert out["changes"] == {
        "start": [{"slot": "FLEX", "player_id": 3916433, "name": "WR Bench", "projected": 10.02}],
        "sit": [],
        "gain": 10.02,
    }


def test_shape_projections_bye_and_missing_projection(roster_settings_json, projections_json, pro_schedules_json):
    for team in pro_schedules_json["settings"]["proTeams"]:
        if team["id"] == 11:
            team["byeWeek"] = 2
    projections_json["players"] = [p for p in projections_json["players"] if p["id"] != 4361050]  # drop TE
    out = shapes.shape_projections(*_proj_args(roster_settings_json, projections_json, pro_schedules_json), season=2026, current_week=1)
    rb = next(p for p in out["players"] if p["name"] == "RB One")
    assert rb["opponent"] == "BYE" and rb["kickoff"] is None
    te = next(p for p in out["players"] if p["name"] == "TE One")
    assert te["projected"] is None
    assert out["current_total"] == round(92.76 - 9.96, 2)


def test_shape_projections_empty_inputs():
    out = shapes.shape_projections(1, [], [], {}, {}, season=2026)
    assert out == {"week": 1, "current_week": None, "players": [], "current_total": 0,
                   "suggested_lineup": [], "suggested_total": 0,
                   "changes": {"start": [], "sit": [], "gain": 0}}


def test_shape_projections_ignores_prior_season_stats_listed_first(
    roster_settings_json, projections_json, pro_schedules_json
):
    for p in projections_json["players"]:
        p["player"]["stats"].insert(0, {"seasonId": 2025, "scoringPeriodId": 2, "statSourceId": 1, "appliedTotal": 99.9})
    out = shapes.shape_projections(
        *_proj_args(roster_settings_json, projections_json, pro_schedules_json), season=2026
    )
    assert next(p for p in out["players"] if p["name"] == "RB One")["projected"] == 17.68


def test_shape_standings_rows_and_order(standings_json):
    out = shapes.shape_standings(standings_json, my_team_id=12)
    assert {k: out[k] for k in ("season", "week", "playoff_teams", "playoff_seeding")} == {
        "season": 2026, "week": 1, "playoff_teams": 6, "playoff_seeding": "TOTAL_POINTS_SCORED",
    }
    assert [t["rank"] for t in out["teams"]] == [1, 2, 3, 4]
    assert [t["team_id"] for t in out["teams"]] == [12, 5, 7, 3]
    assert out["teams"][0] == {
        "rank": 1, "team_id": 12, "name": "My Standings Team", "abbrev": "MST", "owner": "Alex Owner",
        "is_me": True, "record": {"wins": 2, "losses": 0, "ties": 0},
        "points_for": 231.5, "points_against": 190.2, "streak": "W2", "games_back": 0.0,
        "projected_rank": 3, "waiver_priority": 5,
        "transactions": {"acquisitions": 1, "drops": 1, "trades": 0, "faab_spent": 12},
        "clinched": None,
    }
    by_id = {t["team_id"]: t for t in out["teams"]}
    assert by_id[5]["owner"] == "espnfan2" and by_id[5]["clinched"] == "CLINCHED_PLAYOFFS"
    assert by_id[7]["owner"] == "Casey" and by_id[7]["streak"] == "L1"
    assert by_id[3]["owner"] is None and by_id[3]["streak"] == "L2" and by_id[3]["games_back"] == 2.0
    assert [t["is_me"] for t in out["teams"]] == [True, False, False, False]


def test_shape_standings_unseeded_teams_sort_by_record_and_ranks_are_gapless(standings_json):
    for t in standings_json["teams"]:
        t["playoffSeed"] = 0
    out = shapes.shape_standings(standings_json, my_team_id=None)
    assert [t["team_id"] for t in out["teams"]] == [12, 5, 7, 3]   # 2-0 231.5, 2-0 220.0, 1-1, 0-2
    assert [t["rank"] for t in out["teams"]] == [1, 2, 3, 4]
    assert not any(t["is_me"] for t in out["teams"])


def test_shape_standings_zero_rank_fields_become_null(standings_json):
    standings_json["teams"][0]["currentProjectedRank"] = 0
    standings_json["teams"][0]["waiverRank"] = 0
    standings_json["teams"][0]["record"]["overall"]["streakType"] = "NONE"
    standings_json["teams"][0]["record"]["overall"]["streakLength"] = 0
    row = shapes.shape_standings(standings_json, my_team_id=12)["teams"][0]
    assert row["projected_rank"] is None and row["waiver_priority"] is None and row["streak"] is None


def test_shape_standings_sparse():
    assert shapes.shape_standings({}, my_team_id=1) == {
        "season": None, "week": None, "playoff_teams": None, "playoff_seeding": None, "teams": [],
    }
    row = shapes.shape_standings({"teams": [{"id": 9}]}, my_team_id=9)["teams"][0]
    assert row["rank"] == 1 and row["is_me"] is True and row["record"] == {"wins": 0, "losses": 0, "ties": 0}
    assert row["owner"] is None and row["transactions"] == {"acquisitions": 0, "drops": 0, "trades": 0, "faab_spent": 0}


def test_shape_comparison_rows(compare_json, pro_schedules_json):
    ordered = [next(p for p in compare_json["players"] if p["id"] == pid) for pid in (4242335, 4361370)]
    rows = shapes.shape_comparison(ordered, compare_json, 2, pro_schedules_json)
    assert [r["name"] for r in rows] == ["Compare Back", "Compare Receiver"]
    back = rows[0]
    assert back == {
        "player_id": 4242335, "name": "Compare Back", "position": "RB", "pro_team": "IND",
        "injury_status": "ACTIVE", "league_status": "ONTEAM", "owned_by": "My Matchup Team",
        "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4242335.png&w=350&h=254",
        "week": {"projected": 17.68, "opponent": "@KC", "kickoff": "2026-09-21T00:20:00Z"},
        "season": {"projected": 315.58, "points": 25.1, "positional_rank": 4, "games": 1, "avg": 25.1},
        "last_3": [25.1],
        "last_season": {"points": 362.3, "games": 4, "avg": 90.58},
        "percent_owned": 99.9, "percent_change": 0.0,
    }
    rec = rows[1]
    assert rec["league_status"] == "FREEAGENT" and rec["owned_by"] is None
    assert rec["week"] == {"projected": 15.55, "opponent": "@BAL", "kickoff": "2026-09-20T17:00:00Z"}
    assert rec["last_season"] == {"points": 268.0, "games": 2, "avg": 134.0}  # wk18 0.0 has no games-played stat
    assert rec["last_3"] == [28.2]


def test_shape_comparison_unknown_id_and_no_last_season(compare_json, pro_schedules_json):
    entry = next(p for p in compare_json["players"] if p["id"] == 4242335)
    entry["player"]["stats"] = [s for s in entry["player"]["stats"] if s["seasonId"] == 2026]
    rows = shapes.shape_comparison([entry, {"id": 99, "error": "ESPN returned no player with id 99."}], compare_json, 2, {})
    assert rows[0]["last_season"] is None and rows[0]["week"]["opponent"] is None
    assert rows[1] == {"player_id": 99, "error": "ESPN returned no player with id 99."}
