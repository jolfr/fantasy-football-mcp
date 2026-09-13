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
