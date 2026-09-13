import dataclasses
import json

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


@respx.mock
async def test_get_matchup_tool(client, matchup_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=matchup_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_matchup", {})
    assert result.data["week"] == 1
    assert result.data["my_team"]["team_id"] == 12
    assert result.data["opponent"]["team_id"] == 11
    assert len(result.data["my_team"]["roster"]) == 4
    views = route.calls.last.request.url.params.get_list("view")
    assert views == ["mMatchup", "mMatchupScore", "mTeam"]


@respx.mock
async def test_get_matchup_tool_missing_period_is_tool_error(client, matchup_json):
    del matchup_json["status"]
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=matchup_json))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="currentMatchupPeriod"):
            await c.call_tool("get_matchup", {})


@respx.mock
async def test_get_matchup_tool_bye_week_is_tool_error(client, matchup_json):
    matchup_json["status"]["currentMatchupPeriod"] = 2
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=matchup_json))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="week 2"):
            await c.call_tool("get_matchup", {})


@respx.mock
async def test_get_free_agents_tool(client, free_agents_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=free_agents_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool(
            "get_free_agents", {"position": "rb", "limit": 5, "sort": "projected"}
        )
    assert result.data["week"] == 1
    assert result.data["position"] == "RB"
    assert result.data["sort"] == "projected"
    assert [p["name"] for p in result.data["players"]] == ["Waiver Back", "Sparse Receiver"]
    assert result.data["players"][0]["season_projected"] == 113.78

    req = route.calls.last.request
    assert req.url.params.get_list("view") == ["kona_player_info", "mStatus"]
    assert json.loads(req.headers["x-fantasy-filter"]) == {
        "players": {
            "filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
            "limit": 5,
            "filterSlotIds": {"value": [2]},
            "sortAppliedStatTotal": {"sortPriority": 1, "sortAsc": False, "value": "102026"},
        }
    }


@respx.mock
async def test_get_free_agents_defaults(client, free_agents_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=free_agents_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_free_agents", {})
    assert result.data["position"] is None
    assert result.data["sort"] == "owned"
    sent = json.loads(route.calls.last.request.headers["x-fantasy-filter"])["players"]
    assert sent["limit"] == 10
    assert "filterSlotIds" not in sent
    assert sent["sortPercOwned"] == {"sortPriority": 1, "sortAsc": False}


@respx.mock
async def test_get_free_agents_invalid_position_is_tool_error(client):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="position must be one of"):
            await c.call_tool("get_free_agents", {"position": "FLEX"})
    assert not route.called
