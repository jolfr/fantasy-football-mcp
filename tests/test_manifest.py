"""Keep manifest.json in step with pyproject.toml, config.py, and server.py."""

import json
import tomllib
from pathlib import Path

from fantasy_mcp.server import INSTRUCTIONS

ROOT = Path(__file__).resolve().parent.parent


def _manifest() -> dict:
    return json.loads((ROOT / "manifest.json").read_text())


def test_manifest_version_matches_pyproject():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert _manifest()["version"] == pyproject["project"]["version"]


def test_manifest_uses_uv_runtime():
    server = _manifest()["server"]
    assert server["type"] == "uv"
    assert server["mcp_config"]["args"] == ["run", "--directory", "${__dirname}", "fantasy-mcp"]


def test_every_user_config_field_maps_to_an_env_var():
    m = _manifest()
    env = m["server"]["mcp_config"]["env"]
    expected = {
        "ESPN_S2": "${user_config.espn_s2}",
        "ESPN_SWID": "${user_config.swid}",
        "ESPN_LEAGUE_ID": "${user_config.league_id}",
        "ESPN_SEASON": "${user_config.season}",
        "ESPN_TEAM_ID": "${user_config.team_id}",
    }
    assert env == expected
    assert set(m["user_config"]) == {"espn_s2", "swid", "league_id", "season", "team_id"}


def test_secrets_are_sensitive_and_required():
    uc = _manifest()["user_config"]
    for key in ("espn_s2", "swid"):
        assert uc[key]["sensitive"] is True
        assert uc[key]["required"] is True
    assert uc["league_id"]["required"] is True
    assert uc["season"]["required"] is False
    assert uc["team_id"]["required"] is False


def test_instructions_name_the_extension_as_displayed():
    assert _manifest()["display_name"] in INSTRUCTIONS
