import datetime as dt

import pytest

from fantasy_mcp.config import ConfigError, Settings, load_settings

REQUIRED = {
    "ESPN_S2": "s2-cookie",
    "ESPN_SWID": "{ABC-123}",
    "ESPN_LEAGUE_ID": "4242",
}


def _set(monkeypatch, **overrides):
    for key in ("ESPN_S2", "ESPN_SWID", "ESPN_LEAGUE_ID", "ESPN_SEASON", "ESPN_TEAM_ID"):
        monkeypatch.delenv(key, raising=False)
    for key, value in {**REQUIRED, **overrides}.items():
        if value is not None:
            monkeypatch.setenv(key, value)


def test_loads_required_and_defaults_season(monkeypatch):
    _set(monkeypatch)
    s = load_settings(load_dotenv_file=False)
    assert s == Settings(
        espn_s2="s2-cookie",
        swid="{ABC-123}",
        league_id=4242,
        season=dt.date.today().year,
        team_id=None,
    )


def test_optional_overrides(monkeypatch):
    _set(monkeypatch, ESPN_SEASON="2024", ESPN_TEAM_ID="7")
    s = load_settings(load_dotenv_file=False)
    assert s.season == 2024
    assert s.team_id == 7


def test_missing_required_lists_all(monkeypatch):
    _set(monkeypatch, ESPN_S2=None, ESPN_LEAGUE_ID=None)
    with pytest.raises(ConfigError) as exc:
        load_settings(load_dotenv_file=False)
    msg = str(exc.value)
    assert "ESPN_S2" in msg
    assert "ESPN_LEAGUE_ID" in msg
    assert "ESPN_SWID" not in msg


def test_non_integer_league_id(monkeypatch):
    _set(monkeypatch, ESPN_LEAGUE_ID="abc")
    with pytest.raises(ConfigError, match="ESPN_LEAGUE_ID"):
        load_settings(load_dotenv_file=False)
