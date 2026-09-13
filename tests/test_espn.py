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
from tests.conftest import LEAGUE_URL


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
    with pytest.raises(EspnAuthError, match="cookies"):
        EspnClient(settings).get("mTeam")


@respx.mock
def test_html_body_raises_auth_error(settings):
    respx.get(LEAGUE_URL).mock(
        return_value=httpx.Response(200, text="<html>login</html>", headers={"content-type": "text/html"})
    )
    with pytest.raises(EspnAuthError, match="cookies"):
        EspnClient(settings).get("mTeam")


@respx.mock
def test_404_raises_not_found(settings):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(404, text="{}"))
    with pytest.raises(EspnNotFoundError, match="4242"):
        EspnClient(settings).get("mTeam")


@respx.mock
def test_other_status_raises_espn_error(settings):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(EspnError, match="500") as exc:
        EspnClient(settings).get("mTeam")
    assert "boom" in str(exc.value)
    assert not isinstance(exc.value, (EspnAuthError, EspnNotFoundError))
