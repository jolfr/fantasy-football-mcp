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


def test_stat_requires_exact_season_match():
    player = {"stats": [
        {"seasonId": 2025, "scoringPeriodId": 0, "statSourceId": 1, "appliedTotal": 999.0},
        {"scoringPeriodId": 0, "statSourceId": 1, "appliedTotal": 555.0},  # unlabeled: never matches
        {"seasonId": 2026, "scoringPeriodId": 0, "statSourceId": 1, "appliedTotal": 100.0},
    ]}
    assert shapes._stat(player, period=0, source=1, season=2026) == 100.0
    assert shapes._stat(player, period=0, source=1, season=2024) is None
    assert shapes._stat(player, period=0, source=0, season=2026) is None
