import json
from pathlib import Path

import pytest

from fantasy_mcp.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"

LEAGUE_URL = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
    "/seasons/2026/segments/0/leagues/4242"
)


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
