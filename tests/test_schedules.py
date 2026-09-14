from fantasy_mcp.schedules import game_context


def test_away_game(pro_schedules_json):
    assert game_context(pro_schedules_json, 11, 2) == {"opponent": "@KC", "kickoff": "2026-09-21T00:20:00Z"}


def test_home_game(pro_schedules_json):
    assert game_context(pro_schedules_json, 33, 2)["opponent"] == "vs NO"


def test_bye_week(pro_schedules_json):
    assert game_context(pro_schedules_json, 11, 13) == {"opponent": "BYE", "kickoff": None}


def test_no_game_that_week_is_bye(pro_schedules_json):
    for team in pro_schedules_json["settings"]["proTeams"]:
        if team["id"] == 11:
            team["proGamesByScoringPeriod"].pop("2")
    assert game_context(pro_schedules_json, 11, 2)["opponent"] == "BYE"


def test_unknown_team_or_empty_schedules(pro_schedules_json):
    assert game_context(pro_schedules_json, 999, 2) == {"opponent": None, "kickoff": None}
    assert game_context({}, 11, 2) == {"opponent": None, "kickoff": None}
    assert game_context(pro_schedules_json, None, 2) == {"opponent": None, "kickoff": None}
