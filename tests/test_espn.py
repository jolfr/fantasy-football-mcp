import dataclasses
import json

import httpx
import pytest
import respx

from fantasy_mcp.espn import (
    EspnAuthError,
    EspnClient,
    EspnError,
    EspnNotFoundError,
)
from tests.conftest import LEAGUE_URL, PLAYERS_URL, SEASON_URL


@respx.mock
def test_get_sends_cookies_and_repeated_views(settings, league_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))

    data = EspnClient(settings).get("mTeam", "mRoster")

    assert data["id"] == 4242
    req = route.calls.last.request
    assert req.url.params.get_list("view") == ["mTeam", "mRoster"]
    cookie = req.headers["cookie"]
    assert "espn_s2=s2-cookie" in cookie
    assert "SWID={ABC-123}" in cookie
    assert "x-fantasy-filter" not in req.headers


@respx.mock
def test_get_sends_fantasy_filter_header(settings, league_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))

    EspnClient(settings).get("mTeam", fantasy_filter={"players": {"limit": 5}})

    header = route.calls.last.request.headers["x-fantasy-filter"]
    assert json.loads(header) == {"players": {"limit": 5}}


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
def test_auth_status_raises_auth_error(settings, status):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(status, text="nope"))
    with pytest.raises(EspnAuthError, match="cookies") as exc:
        EspnClient(settings).get("mTeam")
    assert "s2-cookie" not in str(exc.value)
    assert "ABC-123" not in str(exc.value)


@respx.mock
def test_html_body_raises_auth_error(settings):
    respx.get(LEAGUE_URL).mock(
        return_value=httpx.Response(200, text="<html>login</html>", headers={"content-type": "text/html"})
    )
    with pytest.raises(EspnAuthError, match="cookies") as exc:
        EspnClient(settings).get("mTeam")
    assert "s2-cookie" not in str(exc.value)
    assert "ABC-123" not in str(exc.value)


@respx.mock
def test_404_raises_not_found(settings):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(404, text="{}"))
    with pytest.raises(EspnNotFoundError, match="4242") as exc:
        EspnClient(settings).get("mTeam")
    assert "s2-cookie" not in str(exc.value)
    assert "ABC-123" not in str(exc.value)


@respx.mock
def test_other_status_raises_espn_error(settings):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(EspnError, match="500") as exc:
        EspnClient(settings).get("mTeam")
    assert "boom" in str(exc.value)
    assert not isinstance(exc.value, (EspnAuthError, EspnNotFoundError))
    assert "s2-cookie" not in str(exc.value)
    assert "ABC-123" not in str(exc.value)


@respx.mock
def test_transport_error_raises_espn_error(settings):
    respx.get(LEAGUE_URL).mock(side_effect=httpx.ConnectTimeout("timed out"))
    with pytest.raises(EspnError, match="Could not reach ESPN"):
        EspnClient(settings).get("mTeam")


@respx.mock
def test_find_my_team_id_matches_swid_case_insensitively(settings, league_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    assert EspnClient(settings).find_my_team_id() == 3


@respx.mock
def test_find_my_team_id_uses_configured_override(settings):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    configured = dataclasses.replace(settings, team_id=9)
    assert EspnClient(configured).find_my_team_id() == 9
    assert not route.called


@respx.mock
def test_find_my_team_id_no_match_raises(settings, league_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    stranger = dataclasses.replace(settings, swid="{NOBODY}")
    with pytest.raises(EspnError, match="ESPN_TEAM_ID") as exc:
        EspnClient(stranger).find_my_team_id()
    assert "NOBODY" not in str(exc.value)
    assert "s2-cookie" not in str(exc.value)


def test_find_my_team_id_explains_missing_owner_data(settings):
    client = EspnClient(settings)
    league = {"teams": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]}  # no owners: e.g. mRoster-only payload
    with pytest.raises(EspnError, match="no team owner data"):
        client.find_my_team_id(league)


@respx.mock
def test_get_players_index_request_shape(settings):
    route = respx.get(PLAYERS_URL).mock(
        return_value=httpx.Response(200, json=[{"id": 1, "fullName": "A"}])
    )
    data = EspnClient(settings).get_players_index()
    assert data == [{"id": 1, "fullName": "A"}]
    req = route.calls.last.request
    assert req.url.params["scoringPeriodId"] == "0"
    assert req.url.params["view"] == "players_wl"
    assert json.loads(req.headers["x-fantasy-filter"]) == {"filterActive": {"value": True}}
    assert "espn_s2=s2-cookie" in req.headers["cookie"]


@respx.mock
def test_get_players_index_rejects_non_list(settings):
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json={"oops": 1}))
    with pytest.raises(EspnError, match="players index"):
        EspnClient(settings).get_players_index()


@respx.mock
def test_get_players_index_404_mentions_season_not_league(settings):
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(404, text="{}"))
    with pytest.raises(EspnNotFoundError) as exc:
        EspnClient(settings).get_players_index()
    assert "ESPN_SEASON" in str(exc.value)
    assert "ESPN_LEAGUE_ID" not in str(exc.value)


@respx.mock
def test_get_rejects_non_object_body(settings):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=[1, 2]))
    with pytest.raises(EspnError, match="not an object"):
        EspnClient(settings).get("mTeam")


@respx.mock
def test_get_players_index_auth_error(settings):
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(401, text="nope"))
    with pytest.raises(EspnAuthError, match="cookies"):
        EspnClient(settings).get_players_index()


@respx.mock
def test_get_sends_scoring_period_param(settings, league_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    EspnClient(settings).get("kona_player_info", scoring_period=2)
    assert route.calls.last.request.url.params["scoringPeriodId"] == "2"


@respx.mock
def test_get_omits_scoring_period_by_default(settings, league_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    EspnClient(settings).get("mTeam")
    assert "scoringPeriodId" not in route.calls.last.request.url.params


@respx.mock
def test_get_pro_schedules(settings, pro_schedules_json):
    route = respx.get(SEASON_URL).mock(return_value=httpx.Response(200, json=pro_schedules_json))
    data = EspnClient(settings).get_pro_schedules()
    assert data["settings"]["proTeams"][0]["abbrev"]
    req = route.calls.last.request
    assert req.url.params["view"] == "proTeamSchedules_wl"
    assert "espn_s2=s2-cookie" in req.headers["cookie"]


@respx.mock
def test_get_pro_schedules_rejects_non_object(settings):
    respx.get(SEASON_URL).mock(return_value=httpx.Response(200, json=[1]))
    with pytest.raises(EspnError, match="schedules"):
        EspnClient(settings).get_pro_schedules()
