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


def test_repr_hides_secrets(monkeypatch):
    _set(monkeypatch)
    r = repr(load_settings(load_dotenv_file=False))
    assert "s2-cookie" not in r
    assert "ABC-123" not in r


def test_missing_required_points_at_desktop_and_env(monkeypatch):
    _set(monkeypatch, ESPN_S2=None)
    with pytest.raises(ConfigError) as exc:
        load_settings(load_dotenv_file=False)
    msg = str(exc.value)
    assert "Claude Desktop" in msg
    assert ".env" in msg


def test_unresolved_placeholder_optionals_are_treated_as_unset(monkeypatch):
    # Claude Desktop leaves "${user_config.x}" literal when the form field is blank.
    _set(monkeypatch, ESPN_SEASON="${user_config.season}", ESPN_TEAM_ID="${user_config.team_id}")
    s = load_settings(load_dotenv_file=False)
    assert s.season == dt.date.today().year
    assert s.team_id is None


def test_whitespace_optionals_are_treated_as_unset(monkeypatch):
    _set(monkeypatch, ESPN_SEASON="  ", ESPN_TEAM_ID=" ")
    s = load_settings(load_dotenv_file=False)
    assert s.season == dt.date.today().year
    assert s.team_id is None


def test_unresolved_placeholder_required_reports_missing(monkeypatch):
    _set(monkeypatch, ESPN_LEAGUE_ID="${user_config.league_id}")
    with pytest.raises(ConfigError, match="not configured"):
        load_settings(load_dotenv_file=False)


def test_values_are_stripped(monkeypatch):
    _set(monkeypatch, ESPN_S2=" s2 ", ESPN_TEAM_ID=" 7 ")
    s = load_settings(load_dotenv_file=False)
    assert s.espn_s2 == "s2"
    assert s.team_id == 7


def test_saved_file_overrides_env(monkeypatch):
    from fantasy_mcp import settings_store

    _set(monkeypatch, ESPN_LEAGUE_ID="1", ESPN_S2="env-s2")
    settings_store.save({"ESPN_S2": "file-s2", "ESPN_LEAGUE_ID": "99"})
    s = load_settings(load_dotenv_file=False)
    assert s.espn_s2 == "file-s2"
    assert s.league_id == 99
    assert s.swid == "{ABC-123}"  # not in the file, so env still supplies it


def test_saved_file_alone_is_enough(monkeypatch):
    from fantasy_mcp import settings_store

    _set(monkeypatch, ESPN_S2=None, ESPN_SWID=None, ESPN_LEAGUE_ID=None)
    settings_store.save({"ESPN_S2": "s2", "ESPN_SWID": "{X}", "ESPN_LEAGUE_ID": "7", "ESPN_TEAM_ID": "3"})
    s = load_settings(load_dotenv_file=False)
    assert (s.espn_s2, s.swid, s.league_id, s.team_id) == ("s2", "{X}", 7, 3)


def test_missing_config_message_names_setup(monkeypatch):
    _set(monkeypatch, ESPN_S2=None)
    with pytest.raises(ConfigError, match="setup"):
        load_settings(load_dotenv_file=False)
