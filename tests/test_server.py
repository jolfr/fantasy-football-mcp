import dataclasses
import json

import httpx
import pytest
import respx
from fastmcp import Client
from fastmcp.exceptions import ToolError

from fantasy_mcp import server
from fantasy_mcp.espn import EspnClient
from fantasy_mcp.server import INSTRUCTIONS
from fantasy_mcp.shapes import shape_player_card
from tests.conftest import LEAGUE_URL, PLAYERS_URL, SEASON_URL


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
async def test_get_free_agents_missing_period_is_tool_error(client, free_agents_json):
    del free_agents_json["scoringPeriodId"]
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=free_agents_json))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="scoringPeriodId"):
            await c.call_tool("get_free_agents", {})


@respx.mock
async def test_get_free_agents_invalid_position_is_tool_error(client):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="position must be one of"):
            await c.call_tool("get_free_agents", {"position": "FLEX"})
    assert not route.called


@pytest.fixture
def cached_index(players_index):
    server.set_players_index_for_tests(players_index)
    yield players_index
    server.set_players_index_for_tests(None)


@respx.mock
async def test_get_player_by_name(client, cached_index, player_card_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=player_card_json))
    index_route = respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json=[]))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_player", {"name": "jonathan taylor"})
    profile = json.loads(result.content[0].text)
    assert profile["player_id"] == 4242335
    assert profile["name"] == "Card Back"
    assert profile["owned_by"]["team_id"] == 12
    assert result.structured_content["$prefab"]["version"]
    assert result.structured_content["view"]["type"] == "Div"
    assert profile == shape_player_card(player_card_json["players"][0], player_card_json)
    assert "\\u" not in result.content[0].text  # non-ASCII (e.g. em dashes) is not escaped
    assert not index_route.called  # cache injected, no index fetch
    req = route.calls.last.request
    assert req.url.params.get_list("view") == ["kona_playercard", "mTeam", "mStatus"]
    sent = json.loads(req.headers["x-fantasy-filter"])["players"]
    assert sent["filterIds"] == {"value": [4242335]}
    assert len(sent["filterStatsForTopScoringPeriodIds"]["additionalValue"]) == 21


@respx.mock
async def test_get_player_by_id_skips_index(client, player_card_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=player_card_json))
    index_route = respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json=[]))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_player", {"player_id": 4242335})
    assert json.loads(result.content[0].text)["player_id"] == 4242335
    assert not index_route.called


@respx.mock
async def test_get_player_fetches_and_caches_index(client, players_index, player_card_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=player_card_json))
    index_route = respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json=players_index))
    server.set_players_index_for_tests(None)
    try:
        async with Client(server.mcp) as c:
            await c.call_tool("get_player", {"name": "Jonathan Taylor"})
            await c.call_tool("get_player", {"name": "Jonathan Taylor"})
    finally:
        server.set_players_index_for_tests(None)
    assert index_route.call_count == 1


@respx.mock
@pytest.mark.parametrize("args", [{}, {"name": "x", "player_id": 1}])
async def test_get_player_requires_exactly_one_arg(client, args):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="exactly one of name or player_id"):
            await c.call_tool("get_player", args)
    assert not route.called


@respx.mock
async def test_get_player_ambiguous_name_is_tool_error(client, cached_index):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="id 4572680"):
            await c.call_tool("get_player", {"name": "tucker"})
    assert not route.called


@respx.mock
async def test_get_player_unknown_id_is_tool_error(client):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={"players": [], "teams": []}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="no player with id 42"):
            await c.call_tool("get_player", {"player_id": 42})


async def test_get_player_is_registered_as_an_app(client):
    async with Client(server.mcp) as c:
        tools = await c.list_tools()
    tool = next(t for t in tools if t.name == "get_player")
    assert tool.meta["ui"]["resourceUri"].startswith("ui://prefab/")
    assert all("ui" not in (t.meta or {}) for t in tools if t.name != "get_player")


@respx.mock
async def test_get_player_card_failure_still_returns_json(client, player_card_json, monkeypatch):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=player_card_json))

    def boom(profile):
        raise RuntimeError("render bug")

    monkeypatch.setattr(server, "player_card", boom)
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_player", {"player_id": 4242335})
    assert json.loads(result.content[0].text)["player_id"] == 4242335
    assert not (result.structured_content or {}).get("$prefab")


@respx.mock
async def test_get_league_settings_tool(client, league_settings_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_settings_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_league_settings", {})
    assert result.data["league_name"] == "Test League"
    assert result.data["scoring"]["ppr"] == 1
    assert result.data["roster"]["lineup"]["FLEX"] == 1
    assert route.calls.last.request.url.params.get_list("view") == ["mSettings"]


def test_instructions_name_both_config_locations():
    assert "Settings → Extensions" in INSTRUCTIONS
    assert ".env" in INSTRUCTIONS
    assert "server's .env file" not in INSTRUCTIONS


@pytest.fixture
def cached_schedules(pro_schedules_json):
    server.set_pro_schedules_for_tests(pro_schedules_json)
    yield pro_schedules_json
    server.set_pro_schedules_for_tests(None)


@respx.mock
async def test_get_projections_tool(client, cached_schedules, roster_settings_json, projections_json):
    def respond(request):
        views = request.url.params.get_list("view")
        return httpx.Response(200, json=projections_json if "kona_player_info" in views else roster_settings_json)

    route = respx.get(LEAGUE_URL).mock(side_effect=respond)
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_projections", {"week": 2})
    assert result.data["week"] == 2
    assert result.data["changes"]["start"][0]["name"] == "WR Bench"
    calls = [r.request for r in route.calls]
    assert calls[0].url.params.get_list("view") == ["mRoster", "mSettings"]
    assert calls[1].url.params.get_list("view") == ["kona_player_info"]
    assert calls[1].url.params["scoringPeriodId"] == "2"
    sent = json.loads(calls[1].headers["x-fantasy-filter"])["players"]["filterIds"]["value"]
    assert 4242335 in sent and len(sent) == 8


@respx.mock
async def test_get_projections_defaults_to_current_week(client, cached_schedules, roster_settings_json, projections_json):
    def respond(request):
        views = request.url.params.get_list("view")
        return httpx.Response(200, json=projections_json if "kona_player_info" in views else roster_settings_json)

    route = respx.get(LEAGUE_URL).mock(side_effect=respond)
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_projections", {})
    assert result.data["week"] == 1
    assert route.calls[1].request.url.params["scoringPeriodId"] == "1"


@respx.mock
@pytest.mark.parametrize("week", [0, 19])
async def test_get_projections_rejects_bad_week(client, week):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="week must be between 1 and 18"):
            await c.call_tool("get_projections", {"week": week})
    assert not route.called


@respx.mock
async def test_get_standings_tool(client, standings_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=standings_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_standings", {})
    assert route.calls.last.request.url.params.get_list("view") == ["mTeam", "mStandings", "mSettings"]
    assert [t["is_me"] for t in result.data["teams"]] == [True, False, False, False]
    assert result.data["teams"][0]["owner"] == "Alex Owner"


@respx.mock
async def test_get_standings_without_a_matching_team_still_returns(settings, standings_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=standings_json))
    server.set_client_for_tests(EspnClient(dataclasses.replace(settings, swid="{NOBODY}")))
    try:
        async with Client(server.mcp) as c:
            result = await c.call_tool("get_standings", {})
    finally:
        server.set_client_for_tests(None)
    assert len(result.data["teams"]) == 4 and not any(t["is_me"] for t in result.data["teams"])


@respx.mock
async def test_compare_players_tool(client, cached_index, cached_schedules, compare_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=compare_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("compare_players", {"players": ["Jonathan Taylor", "4361370"], "week": 2})
    req = route.calls.last.request
    assert req.url.params.get_list("view") == ["kona_playercard", "mTeam", "mStatus"]
    assert req.url.params["scoringPeriodId"] == "2"
    assert json.loads(req.headers["x-fantasy-filter"])["players"]["filterIds"]["value"] == [4242335, 4361370]
    assert [p["name"] for p in result.data["players"]] == ["Compare Back", "Compare Receiver"]
    assert result.data["players"][0]["week"]["projected"] == 17.68
    assert "unresolved" not in result.data


@respx.mock
async def test_compare_players_default_week_reads_status_first(client, cached_index, cached_schedules, compare_json):
    def respond(request):
        views = request.url.params.get_list("view")
        if views == ["mStatus"]:
            return httpx.Response(200, json={"status": {"currentMatchupPeriod": 1}})
        return httpx.Response(200, json=compare_json)

    route = respx.get(LEAGUE_URL).mock(side_effect=respond)
    async with Client(server.mcp) as c:
        result = await c.call_tool("compare_players", {"players": [4242335, 4361370]})
    assert result.data["week"] == 1
    assert route.calls[0].request.url.params.get_list("view") == ["mStatus"]
    assert route.calls[1].request.url.params["scoringPeriodId"] == "1"


@respx.mock
async def test_compare_players_partial_resolution(client, cached_index, cached_schedules, compare_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=compare_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("compare_players", {"players": ["Jonathan Taylor", "tucker"], "week": 2})
    assert [p["name"] for p in result.data["players"]] == ["Compare Back"]
    assert result.data["unresolved"][0]["input"] == "tucker"
    assert "id 4572680" in result.data["unresolved"][0]["error"]


@respx.mock
@pytest.mark.parametrize("players", [["a"], ["a", "b", "c", "d", "e", "f", "g"]])
async def test_compare_players_count_validation(client, players):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="between 2 and 6"):
            await c.call_tool("compare_players", {"players": players})
    assert not route.called


@respx.mock
async def test_compare_players_all_unresolved_is_tool_error(client, cached_index):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="Nobody Real"):
            await c.call_tool("compare_players", {"players": ["Nobody Real", "Nobody Else"], "week": 2})
    assert not route.called



@respx.mock
async def test_get_projections_fetches_and_caches_schedules(client, roster_settings_json, projections_json, pro_schedules_json):
    def respond(request):
        views = request.url.params.get_list("view")
        return httpx.Response(200, json=projections_json if "kona_player_info" in views else roster_settings_json)

    respx.get(LEAGUE_URL).mock(side_effect=respond)
    sched = respx.get(SEASON_URL).mock(return_value=httpx.Response(200, json=pro_schedules_json))
    server.set_pro_schedules_for_tests(None)
    try:
        async with Client(server.mcp) as c:
            await c.call_tool("get_projections", {"week": 2})
            result = await c.call_tool("get_projections", {"week": 2})
    finally:
        server.set_pro_schedules_for_tests(None)
    assert sched.call_count == 1
    assert result.data["players"][1]["opponent"] == "@KC"


@respx.mock
async def test_get_matchup_past_or_future_week(client, matchup_json):
    matchup_json["schedule"][1]["home"]["teamId"] = 12  # give team 12 a period-2 game
    matchup_json["scoringPeriodId"] = 2
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=matchup_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_matchup", {"week": 2})
    assert route.calls.last.request.url.params["scoringPeriodId"] == "2"
    assert result.data["week"] == 2 and result.data["current_week"] == 1
    assert result.data["status"] == "UPCOMING"


@respx.mock
async def test_get_matchup_default_has_no_scoring_period(client, matchup_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=matchup_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_matchup", {})
    assert "scoringPeriodId" not in route.calls.last.request.url.params
    assert result.data["week"] == 1 and result.data["current_week"] == 1


@respx.mock
@pytest.mark.parametrize("week", [0, 19])
async def test_get_matchup_rejects_bad_week(client, week):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="week must be between 1 and 18"):
            await c.call_tool("get_matchup", {"week": week})
    assert not route.called


@respx.mock
@pytest.mark.parametrize("team, expected_id", [(5, 5), ("5", 5), ("MYS", 3), ("rival", 5)])
async def test_get_team_tool(client, league_json, team, expected_id):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_team", {"team": team})
    assert route.calls.last.request.url.params.get_list("view") == ["mTeam", "mRoster"]
    assert result.data["team_id"] == expected_id
    assert "owner" in result.data
    if expected_id == 3:
        assert next(p for p in result.data["roster"] if p["name"] == "Josh Allen")["projected"] == 22.4


@respx.mock
async def test_get_team_unknown_lists_teams(client, league_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match=r"Rival Team \(RIV, id 5\)"):
            await c.call_tool("get_team", {"team": "nobody"})


@respx.mock
async def test_get_my_team_rows_now_include_projected(client, league_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_my_team", {})
    assert result.data["owner"] == "Alex Owner"
    assert next(p for p in result.data["roster"] if p["name"] == "Josh Allen")["projected"] == 22.4


async def test_ten_tools_registered(client):
    async with Client(server.mcp) as c:
        names = sorted(t.name for t in await c.list_tools())
    assert names == ["compare_players", "get_free_agents", "get_league_settings", "get_matchup", "get_my_team",
                     "get_player", "get_projections", "get_standings", "get_team", "whoami"]
