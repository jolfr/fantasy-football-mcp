"""Keep manifest.json in step with pyproject.toml, config.py, and server.py."""

import json
import tomllib
from pathlib import Path

from fantasy_mcp.config import _REQUIRED
from fantasy_mcp.server import INSTRUCTIONS

ROOT = Path(__file__).resolve().parent.parent


def _manifest() -> dict:
    return json.loads((ROOT / "manifest.json").read_text())


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_manifest_version_matches_pyproject():
    assert _manifest()["version"] == _pyproject()["project"]["version"]


def test_python_requirement_matches_pyproject():
    runtimes = _manifest()["compatibility"]["runtimes"]
    assert runtimes["python"] == _pyproject()["project"]["requires-python"]


def test_manifest_runs_the_console_script_with_uv():
    server = _manifest()["server"]
    args = server["mcp_config"]["args"]
    assert server["type"] == "uv"
    assert server["mcp_config"]["command"] == "uv"
    assert args[0] == "run"
    assert "--no-dev" in args and "--frozen" in args
    assert args[-1] in _pyproject()["project"]["scripts"]


def test_required_env_vars_are_all_injected():
    env = _manifest()["server"]["mcp_config"]["env"]
    assert set(_REQUIRED) <= set(env)


def test_env_vars_and_form_fields_are_one_to_one():
    m = _manifest()
    env = m["server"]["mcp_config"]["env"]
    expected = {f"${{user_config.{key}}}" for key in m["user_config"]}
    assert set(env.values()) == expected
    assert len(env) == len(m["user_config"])


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
