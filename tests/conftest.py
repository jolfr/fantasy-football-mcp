import json
from pathlib import Path

import pytest

from fantasy_mcp.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"

LEAGUE_URL = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
    "/seasons/2026/segments/0/leagues/4242"
)

PLAYERS_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/players"

SEASON_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        espn_s2="s2-cookie",
        swid="{ABC-123}",
        league_id=4242,
        season=2026,
        team_id=None,
    )


@pytest.fixture
def league_json() -> dict:
    return json.loads((FIXTURES / "mteam_mroster.json").read_text())


@pytest.fixture
def matchup_json() -> dict:
    return json.loads((FIXTURES / "matchup.json").read_text())


@pytest.fixture
def free_agents_json() -> dict:
    return json.loads((FIXTURES / "free_agents.json").read_text())


@pytest.fixture
def players_index() -> list:
    return json.loads((FIXTURES / "players_index.json").read_text())


@pytest.fixture
def player_card_json() -> dict:
    return json.loads((FIXTURES / "player_card.json").read_text())


@pytest.fixture
def league_settings_json() -> dict:
    return json.loads((FIXTURES / "league_settings.json").read_text())


@pytest.fixture
def roster_settings_json() -> dict:
    return json.loads((FIXTURES / "roster_settings.json").read_text())


@pytest.fixture
def projections_json() -> dict:
    return json.loads((FIXTURES / "projections.json").read_text())


@pytest.fixture
def pro_schedules_json() -> dict:
    return json.loads((FIXTURES / "pro_schedules.json").read_text())


@pytest.fixture
def standings_json() -> dict:
    return json.loads((FIXTURES / "standings.json").read_text())


@pytest.fixture
def compare_json() -> dict:
    return json.loads((FIXTURES / "compare.json").read_text())


@pytest.fixture(autouse=True)
def isolated_config_path(tmp_path, monkeypatch):
    """Every test gets its own settings file; never read or write the developer's real one."""
    from fantasy_mcp import settings_store

    path = tmp_path / "fantasy-mcp" / "config.json"
    monkeypatch.setattr(settings_store, "config_path", lambda: path)
    return path
