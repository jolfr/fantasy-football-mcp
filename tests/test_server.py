import dataclasses

import httpx
import pytest
import respx
from fastmcp import Client
from fastmcp.exceptions import ToolError

from fantasy_mcp import server
from fantasy_mcp.espn import EspnClient
from tests.conftest import LEAGUE_URL


@pytest.fixture
def client(settings):
    espn = EspnClient(settings)
    server.set_client_for_tests(espn)
    yield espn
    server.set_client_for_tests(None)


def test_shape_team_orders_starters_first_and_maps_ids(league_json):
    team = league_json["teams"][0]
    shaped = server.shape_team(team)

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
    shaped = server.shape_team(team)
    ir_row = shaped["roster"][-1]
    assert ir_row["slot"] == "IR"
    assert ir_row["name"] is None
    assert ir_row["position"] == "UNKNOWN_-1"


def test_shape_whoami(league_json, settings):
    out = server.shape_whoami(league_json, team_id=3, settings=settings)
    assert out == {
        "league_id": 4242,
        "season": 2026,
        "league_name": "Test League",
        "team_id": 3,
        "team_name": "My Squad",
    }


def test_team_by_id_missing_raises(league_json):
    with pytest.raises(server.EspnError, match="ESPN_TEAM_ID"):
        server.team_by_id(league_json, 42)


@respx.mock
async def test_whoami_tool(client, league_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("whoami", {})
    assert result.data["team_name"] == "My Squad"
    assert result.data["league_name"] == "Test League"
    # League name only comes back with mSettings; mTeam alone has no "settings" key.
    assert route.calls.last.request.url.params.get_list("view") == ["mTeam", "mSettings"]


@respx.mock
async def test_get_my_team_tool(client, league_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_my_team", {})
    assert result.data["team_id"] == 3
    assert len(result.data["roster"]) == 3


@respx.mock
async def test_tool_surfaces_auth_error(client):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(401, text="nope"))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="cookies"):
            await c.call_tool("whoami", {})


@respx.mock
async def test_tool_surfaces_bad_configured_team_id(settings, league_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    server.set_client_for_tests(EspnClient(dataclasses.replace(settings, team_id=42)))
    try:
        async with Client(server.mcp) as c:
            with pytest.raises(ToolError, match="ESPN_TEAM_ID"):
                await c.call_tool("get_my_team", {})
    finally:
        server.set_client_for_tests(None)
