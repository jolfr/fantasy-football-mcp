# ESPN Fantasy MCP (Basic) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A stdio MCP server that authenticates to a private ESPN fantasy football league with `espn_s2`/`SWID` cookies and exposes `whoami` and `get_my_team` tools.

**Architecture:** A small `EspnClient` (httpx) wraps the ESPN v3 `leagues/{id}?view=...` endpoint and maps HTTP failures to typed exceptions. `config.py` loads settings from env/`.env`. `ids.py` maps ESPN numeric IDs to names. `server.py` defines the FastMCP tools and shapes the JSON Claude sees.

**Tech Stack:** Python 3.12, uv, fastmcp 4.0.3, httpx, python-dotenv; tests with pytest + respx.

**Spec:** `docs/superpowers/specs/2026-09-13-espn-mcp-basic-design.md`

---

## File structure

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | deps, dev deps, `fantasy-mcp` script entry, pytest config |
| `src/fantasy_mcp/__init__.py` | empty package marker |
| `src/fantasy_mcp/config.py` | `Settings` dataclass + `load_settings()` from env/.env |
| `src/fantasy_mcp/ids.py` | `POSITIONS`, `LINEUP_SLOTS`, `PRO_TEAMS` dicts + `name()` |
| `src/fantasy_mcp/espn.py` | `EspnClient`, `EspnError` hierarchy |
| `src/fantasy_mcp/server.py` | FastMCP app, `whoami`, `get_my_team`, `main()` |
| `tests/conftest.py` | shared `settings` fixture |
| `tests/fixtures/mteam_mroster.json` | scrubbed ESPN response |
| `tests/test_config.py`, `test_ids.py`, `test_espn.py`, `test_server.py` | tests |
| `.env.example` | documents env vars |
| `README.md` | setup + Claude Code registration |

Notes for the engineer:
- Run everything with `uv run ...` — it manages the venv.
- `uv add <pkg>` adds a runtime dep; `uv add --dev <pkg>` adds a dev dep. Both update `pyproject.toml` and `uv.lock`.
- Commit messages follow Conventional Commits (`feat:`, `test:`, `chore:`, `docs:`).

---

### Task 1: Project scaffolding

**Files:**
- Modify: `pyproject.toml`
- Create: `src/fantasy_mcp/__init__.py`
- Create: `tests/__init__.py` (makes `from tests.conftest import ...` resolvable)
- Delete: `main.py`
- Create: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Add dependencies**

```bash
cd /Users/jcarroll/Repositories/fantasy-mcp
uv add httpx python-dotenv
uv add --dev pytest respx pytest-asyncio
```

Expected: `pyproject.toml` gains the deps; `uv.lock` updated.

- [ ] **Step 2: Rewrite `pyproject.toml`**

Replace the whole file with (keep whatever version pins `uv add` wrote for the deps):

```toml
[project]
name = "fantasy-mcp"
version = "0.1.0"
description = "MCP server exposing ESPN fantasy football team data"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastmcp>=4.0.3",
    "httpx>=0.27",
    "python-dotenv>=1.0",
]

[project.scripts]
fantasy-mcp = "fantasy_mcp.server:main"

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/fantasy_mcp"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 3: Create package, remove old entry, add env example**

```bash
mkdir -p src/fantasy_mcp tests/fixtures
touch src/fantasy_mcp/__init__.py tests/__init__.py
git rm -q main.py
cat > .env.example <<'EOF'
# Copy to .env and fill in. Get cookies from your browser's dev tools
# (Application > Cookies > espn.com) while logged in to ESPN.
ESPN_S2=
ESPN_SWID={XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}
ESPN_LEAGUE_ID=
# Optional: defaults to the current calendar year
# ESPN_SEASON=2026
# Optional: skip owner lookup and use this team id directly
# ESPN_TEAM_ID=
EOF
printf '\n# Secrets\n.env\n' >> .gitignore
```

- [ ] **Step 4: Verify the project still resolves**

Run: `uv sync && uv run python -c "import fantasy_mcp, httpx, dotenv, respx; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: scaffold fantasy_mcp package and dependencies"
```

---

### Task 2: Settings loader (`config.py`)

**Files:**
- Create: `src/fantasy_mcp/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_mcp.config'`

- [ ] **Step 3: Implement `config.py`**

`src/fantasy_mcp/config.py`:

```python
"""Load ESPN settings from the environment (with .env fallback)."""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when required configuration is missing or malformed."""


@dataclass(frozen=True)
class Settings:
    espn_s2: str
    swid: str
    league_id: int
    season: int
    team_id: int | None


_REQUIRED = ("ESPN_S2", "ESPN_SWID", "ESPN_LEAGUE_ID")


def _int(name: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from e


def load_settings(load_dotenv_file: bool = True) -> Settings:
    if load_dotenv_file:
        load_dotenv()

    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        raise ConfigError(
            "Missing required environment variables: " + ", ".join(missing)
            + ". Copy .env.example to .env and fill them in."
        )

    season_raw = os.environ.get("ESPN_SEASON")
    team_raw = os.environ.get("ESPN_TEAM_ID")

    return Settings(
        espn_s2=os.environ["ESPN_S2"],
        swid=os.environ["ESPN_SWID"],
        league_id=_int("ESPN_LEAGUE_ID", os.environ["ESPN_LEAGUE_ID"]),
        season=_int("ESPN_SEASON", season_raw) if season_raw else dt.date.today().year,
        team_id=_int("ESPN_TEAM_ID", team_raw) if team_raw else None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/config.py tests/test_config.py
git commit -m "feat: load ESPN settings from environment"
```

---

### Task 3: ID maps (`ids.py`)

**Files:**
- Create: `src/fantasy_mcp/ids.py`
- Create: `tests/test_ids.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_ids.py`:

```python
from fantasy_mcp.ids import LINEUP_SLOTS, POSITIONS, PRO_TEAMS, name


def test_known_ids():
    assert name(POSITIONS, 1) == "QB"
    assert name(LINEUP_SLOTS, 20) == "BENCH"
    assert name(LINEUP_SLOTS, 23) == "FLEX"
    assert name(PRO_TEAMS, 2) == "BUF"


def test_unknown_id_falls_back():
    assert name(POSITIONS, 999) == "UNKNOWN_999"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ids.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_mcp.ids'`

- [ ] **Step 3: Implement `ids.py`**

`src/fantasy_mcp/ids.py`:

```python
"""ESPN numeric ID -> human name lookup tables."""

from __future__ import annotations

# player.defaultPositionId
POSITIONS: dict[int, str] = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
    5: "K",
    7: "P",
    9: "DT",
    10: "DE",
    11: "LB",
    12: "CB",
    13: "S",
    14: "HC",
    16: "D/ST",
}

# roster.entries[].lineupSlotId
LINEUP_SLOTS: dict[int, str] = {
    0: "QB",
    1: "TQB",
    2: "RB",
    3: "RB/WR",
    4: "WR",
    5: "WR/TE",
    6: "TE",
    7: "OP",
    8: "DT",
    9: "DE",
    10: "LB",
    11: "DL",
    12: "CB",
    13: "S",
    14: "DB",
    15: "DP",
    16: "D/ST",
    17: "K",
    18: "P",
    19: "HC",
    20: "BENCH",
    21: "IR",
    22: "UNKNOWN_22",
    23: "FLEX",
    24: "EDR",
    25: "RB/WR/TE",
}

# player.proTeamId
PRO_TEAMS: dict[int, str] = {
    0: "FA",
    1: "ATL",
    2: "BUF",
    3: "CHI",
    4: "CIN",
    5: "CLE",
    6: "DAL",
    7: "DEN",
    8: "DET",
    9: "GB",
    10: "TEN",
    11: "IND",
    12: "KC",
    13: "LV",
    14: "LAR",
    15: "MIA",
    16: "MIN",
    17: "NE",
    18: "NO",
    19: "NYG",
    20: "NYJ",
    21: "PHI",
    22: "ARI",
    23: "PIT",
    24: "LAC",
    25: "SF",
    26: "SEA",
    27: "TB",
    28: "WSH",
    29: "CAR",
    30: "JAX",
    33: "BAL",
    34: "HOU",
}


def name(table: dict[int, str], id_: int) -> str:
    """Return the name for ``id_`` or ``UNKNOWN_<id>`` if unmapped."""
    return table.get(id_, f"UNKNOWN_{id_}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ids.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/ids.py tests/test_ids.py
git commit -m "feat: add ESPN id lookup tables"
```

---

### Task 4: Test fixture and conftest

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/fixtures/mteam_mroster.json`

This fixture is a hand-trimmed, scrubbed shape of an ESPN `?view=mTeam&view=mRoster` response. It contains exactly the keys the code reads. (Once the server runs against the real league, the engineer may replace it with a real scrubbed capture — keep the same team/owner IDs so tests stay valid.)

- [ ] **Step 1: Create the fixture**

`tests/fixtures/mteam_mroster.json`:

```json
{
  "id": 4242,
  "seasonId": 2026,
  "settings": {"name": "Test League"},
  "members": [
    {"id": "{ABC-123}", "displayName": "me"},
    {"id": "{DEF-456}", "displayName": "rival"}
  ],
  "teams": [
    {
      "id": 3,
      "name": "My Squad",
      "abbrev": "MYS",
      "owners": ["{abc-123}"],
      "record": {
        "overall": {"wins": 1, "losses": 0, "ties": 0, "pointsFor": 128.4, "pointsAgainst": 101.2}
      },
      "roster": {
        "entries": [
          {
            "lineupSlotId": 20,
            "playerPoolEntry": {
              "player": {"fullName": "Bench Guy", "defaultPositionId": 2, "proTeamId": 6, "injuryStatus": "QUESTIONABLE"}
            }
          },
          {
            "lineupSlotId": 0,
            "playerPoolEntry": {
              "player": {"fullName": "Josh Allen", "defaultPositionId": 1, "proTeamId": 2, "injuryStatus": "ACTIVE"}
            }
          },
          {
            "lineupSlotId": 23,
            "playerPoolEntry": {
              "player": {"fullName": "Flex Player", "defaultPositionId": 3, "proTeamId": 99, "injuryStatus": "ACTIVE"}
            }
          }
        ]
      }
    },
    {
      "id": 5,
      "name": "Rival Team",
      "abbrev": "RIV",
      "owners": ["{DEF-456}"],
      "record": {
        "overall": {"wins": 0, "losses": 1, "ties": 0, "pointsFor": 101.2, "pointsAgainst": 128.4}
      },
      "roster": {"entries": []}
    }
  ]
}
```

Note: team 3's owner SWID is deliberately lower-cased (`{abc-123}`) while the configured SWID is `{ABC-123}` — this exercises the case-insensitive match.

- [ ] **Step 2: Create `tests/conftest.py`**

```python
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
```

- [ ] **Step 3: Verify it loads**

Run: `uv run pytest tests -v`
Expected: 6 passed (existing tests still pass; conftest imports OK)

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/fixtures/mteam_mroster.json
git commit -m "test: add scrubbed ESPN league fixture"
```

---

### Task 5: `EspnClient.get` — request shape and error mapping

**Files:**
- Create: `src/fantasy_mcp/espn.py`
- Create: `tests/test_espn.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_espn.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_espn.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_mcp.espn'`

- [ ] **Step 3: Implement `espn.py` (client + errors, no team lookup yet)**

`src/fantasy_mcp/espn.py`:

```python
"""Minimal ESPN fantasy football v3 API client."""

from __future__ import annotations

import json
from typing import Any

import httpx

from fantasy_mcp.config import Settings

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
TIMEOUT_SECONDS = 15.0


class EspnError(Exception):
    """Base error for ESPN API failures."""


class EspnAuthError(EspnError):
    """Cookies missing, invalid, or expired."""


class EspnNotFoundError(EspnError):
    """League/season not found."""


class EspnClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.league_url = (
            f"{BASE}/seasons/{settings.season}/segments/0/leagues/{settings.league_id}"
        )
        self._cookies = {"espn_s2": settings.espn_s2, "SWID": settings.swid}

    def get(self, *views: str, fantasy_filter: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET the league endpoint with one or more ``view`` params."""
        headers = {"Accept": "application/json"}
        if fantasy_filter is not None:
            headers["X-Fantasy-Filter"] = json.dumps(fantasy_filter)

        response = httpx.get(
            self.league_url,
            params=[("view", v) for v in views],
            cookies=self._cookies,
            headers=headers,
            timeout=TIMEOUT_SECONDS,
        )
        return self._parse(response)

    def _parse(self, response: httpx.Response) -> dict[str, Any]:
        status = response.status_code
        if status in (401, 403):
            raise EspnAuthError(
                f"ESPN returned {status}. Your espn_s2/SWID cookies are missing, "
                "invalid, or expired — refresh them from your browser."
            )
        if status == 404:
            s = self.settings
            raise EspnNotFoundError(
                f"ESPN returned 404 for league {s.league_id}, season {s.season}. "
                "Check ESPN_LEAGUE_ID and ESPN_SEASON."
            )
        if status >= 400:
            raise EspnError(f"ESPN returned HTTP {status}: {response.text[:200]}")

        try:
            return response.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise EspnAuthError(
                "ESPN returned a non-JSON response (likely a login page). "
                "Your espn_s2/SWID cookies are probably expired."
            ) from e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_espn.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/espn.py tests/test_espn.py
git commit -m "feat: add EspnClient with cookie auth and error mapping"
```

---

### Task 6: `EspnClient.find_my_team_id`

**Files:**
- Modify: `src/fantasy_mcp/espn.py`
- Modify: `tests/test_espn.py`

- [ ] **Step 1: Append failing tests to `tests/test_espn.py`**

Add `import dataclasses` to the imports at the top of the file, then append:

```python

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
    with pytest.raises(EspnError, match="ESPN_TEAM_ID"):
        EspnClient(stranger).find_my_team_id()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_espn.py -v -k find_my_team_id`
Expected: 3 FAIL with `AttributeError: 'EspnClient' object has no attribute 'find_my_team_id'`

- [ ] **Step 3: Add the method to `EspnClient`**

Append inside the `EspnClient` class in `src/fantasy_mcp/espn.py`:

```python
    def find_my_team_id(self, league: dict[str, Any] | None = None) -> int:
        """Return the configured team id, or the team whose owners include our SWID.

        ``league`` may be passed to reuse an already-fetched ``mTeam`` payload.
        """
        if self.settings.team_id is not None:
            return self.settings.team_id

        if league is None:
            league = self.get("mTeam")

        swid = self.settings.swid.lower()
        for team in league.get("teams", []):
            owners = [o.lower() for o in team.get("owners", [])]
            if swid in owners:
                return int(team["id"])

        raise EspnError(
            f"No team in league {self.settings.league_id} is owned by SWID "
            f"{self.settings.swid}. Set ESPN_TEAM_ID explicitly."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_espn.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/espn.py tests/test_espn.py
git commit -m "feat: resolve user's team id from SWID"
```

---

### Task 7: MCP server with `whoami` and `get_my_team`

**Files:**
- Create: `src/fantasy_mcp/server.py`
- Create: `tests/test_server.py`

Design notes:
- Pure shaping functions `shape_whoami(league, team_id, settings)` and `shape_team(team)` are separated from the tool functions so they're unit-testable without MCP plumbing.
- The client is built lazily (`_client()`) so importing the module doesn't require env vars; tests inject a client via `set_client_for_tests`.
- Tools are called in tests through `fastmcp.Client(mcp)` in-memory, which verifies registration and error propagation.

- [ ] **Step 1: Write the failing tests**

`tests/test_server.py`:

```python
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


def test_shape_team_orders_starters_first_and_maps_ids(league_json):
    team = league_json["teams"][0]
    shaped = server.shape_team(team)

    assert shaped["team_id"] == 3
    assert shaped["name"] == "My Squad"
    assert shaped["abbrev"] == "MYS"
    assert shaped["record"] == {"wins": 1, "losses": 0, "ties": 0}
    assert shaped["points_for"] == 128.4
    assert shaped["points_against"] == 101.2

    names = [p["name"] for p in shaped["roster"]]
    assert names == ["Josh Allen", "Flex Player", "Bench Guy"]

    allen = shaped["roster"][0]
    assert allen == {
        "name": "Josh Allen",
        "position": "QB",
        "slot": "QB",
        "pro_team": "BUF",
        "injury_status": "ACTIVE",
    }
    assert shaped["roster"][1]["pro_team"] == "UNKNOWN_99"
    assert shaped["roster"][2]["slot"] == "BENCH"


def test_shape_whoami(league_json, settings):
    out = server.shape_whoami(league_json, team_id=3, settings=settings)
    assert out == {
        "league_id": 4242,
        "season": 2026,
        "league_name": "Test League",
        "team_id": 3,
        "team_name": "My Squad",
    }


@respx.mock
async def test_whoami_tool(client, league_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("whoami", {})
    assert result.data["team_name"] == "My Squad"
    assert result.data["league_name"] == "Test League"


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_mcp.server'`

- [ ] **Step 3: Implement `server.py`**

`src/fantasy_mcp/server.py`:

```python
"""FastMCP server exposing ESPN fantasy football tools."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from fantasy_mcp import ids
from fantasy_mcp.config import ConfigError, Settings, load_settings
from fantasy_mcp.espn import EspnClient, EspnError

mcp = FastMCP(
    "fantasy-mcp",
    instructions="Read-only access to the user's ESPN fantasy football league.",
)

_client: EspnClient | None = None


def _get_client() -> EspnClient:
    global _client
    if _client is None:
        _client = EspnClient(load_settings())
    return _client


def set_client_for_tests(client: EspnClient | None) -> None:
    global _client
    _client = client


# --- shaping -----------------------------------------------------------------


def shape_whoami(league: dict[str, Any], team_id: int, settings: Settings) -> dict[str, Any]:
    team = next(t for t in league["teams"] if t["id"] == team_id)
    return {
        "league_id": settings.league_id,
        "season": settings.season,
        "league_name": league.get("settings", {}).get("name"),
        "team_id": team_id,
        "team_name": team.get("name"),
    }


def _shape_player(entry: dict[str, Any]) -> dict[str, Any]:
    player = entry["playerPoolEntry"]["player"]
    return {
        "name": player.get("fullName"),
        "position": ids.name(ids.POSITIONS, player.get("defaultPositionId", -1)),
        "slot": ids.name(ids.LINEUP_SLOTS, entry.get("lineupSlotId", -1)),
        "pro_team": ids.name(ids.PRO_TEAMS, player.get("proTeamId", -1)),
        "injury_status": player.get("injuryStatus"),
    }


def _slot_sort_key(entry: dict[str, Any]) -> tuple[int, int]:
    slot = entry.get("lineupSlotId", 99)
    # Starters (anything not bench/IR) first, then bench, then IR.
    bucket = {20: 1, 21: 2}.get(slot, 0)
    return (bucket, slot)


def shape_team(team: dict[str, Any]) -> dict[str, Any]:
    overall = team.get("record", {}).get("overall", {})
    entries = sorted(team.get("roster", {}).get("entries", []), key=_slot_sort_key)
    return {
        "team_id": team["id"],
        "name": team.get("name"),
        "abbrev": team.get("abbrev"),
        "record": {
            "wins": overall.get("wins", 0),
            "losses": overall.get("losses", 0),
            "ties": overall.get("ties", 0),
        },
        "points_for": overall.get("pointsFor", 0.0),
        "points_against": overall.get("pointsAgainst", 0.0),
        "roster": [_shape_player(e) for e in entries],
    }


# --- tools -------------------------------------------------------------------


@mcp.tool
def whoami() -> dict[str, Any]:
    """Confirm ESPN auth works: return the league name, season, and the user's team."""
    try:
        client = _get_client()
        league = client.get("mTeam")
        team_id = client.find_my_team_id(league)
        return shape_whoami(league, team_id, client.settings)
    except (EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e


@mcp.tool
def get_my_team() -> dict[str, Any]:
    """Return the user's fantasy team: record, points, and full roster with lineup slots."""
    try:
        client = _get_client()
        league = client.get("mTeam", "mRoster")
        team_id = client.find_my_team_id(league)
        team = next(t for t in league["teams"] if t["id"] == team_id)
        return shape_team(team)
    except (EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests -v`
Expected: 21 passed

If `test_shape_team_orders_starters_first_and_maps_ids` fails on order: FLEX (23) must come before BENCH (20). The sort key buckets bench=1, IR=2, everything else=0, so QB(0) → FLEX(23) → BENCH(20). Check `_slot_sort_key`.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/server.py tests/test_server.py
git commit -m "feat: add whoami and get_my_team MCP tools"
```

---

### Task 8: Live smoke test and Claude Code registration

**Files:**
- Create: `.env` (local only, gitignored — never commit)
- Create: `.mcp.json`
- Create: `README.md`

- [ ] **Step 1: Create `.env` from the example**

```bash
cp .env.example .env
```

Fill in `ESPN_S2`, `ESPN_SWID` (with braces), `ESPN_LEAGUE_ID`. The user (Thomas) supplies these values; the engineer must not paste them anywhere else.

- [ ] **Step 2: Run the server entrypoint to confirm it starts**

Run: `timeout 3 uv run fantasy-mcp; echo "exit=$?"`
Expected: FastMCP banner (or silence) then `exit=124` (killed by timeout — meaning it stayed up waiting on stdio). Any traceback = fix before continuing.

- [ ] **Step 3: Call `whoami` for real via the in-memory client**

```bash
uv run python - <<'EOF'
import asyncio
from fastmcp import Client
from fantasy_mcp import server

async def main():
    async with Client(server.mcp) as c:
        print((await c.call_tool("whoami", {})).data)
        team = (await c.call_tool("get_my_team", {})).data
        print(team["name"], team["record"])
        for p in team["roster"]:
            print(f'  {p["slot"]:<6} {p["position"]:<4} {p["name"]:<24} {p["pro_team"]:<4} {p["injury_status"]}')

asyncio.run(main())
EOF
```

Expected: league name + your team, then the roster with real names. If you see `UNKNOWN_<n>` in `slot`/`position`/`pro_team`, note the number and add it to the matching table in `ids.py` (commit as `fix: map ESPN id <n>`).

If you get an auth error: re-copy the cookies (espn_s2 is long and URL-encoded — copy it exactly; SWID must include `{}`).

- [ ] **Step 4: Add `.mcp.json` so Claude Code picks the server up in this repo**

`.mcp.json`:

```json
{
  "mcpServers": {
    "fantasy": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/jcarroll/Repositories/fantasy-mcp", "fantasy-mcp"]
    }
  }
}
```

- [ ] **Step 5: Write `README.md`**

```markdown
# fantasy-mcp

MCP server giving Claude read access to your ESPN fantasy football team.

## Setup

1. `cp .env.example .env`
2. Log in to fantasy.espn.com, open dev tools → Application → Cookies → `espn.com`,
   and copy `espn_s2` and `SWID` (keep the curly braces) into `.env`.
3. Set `ESPN_LEAGUE_ID` (from your league URL: `leagueId=...`).
4. `uv sync`

## Use with Claude Code

`.mcp.json` in this repo registers the server automatically when you run
`claude` here. For other projects or Claude Desktop, add:

```json
{"mcpServers": {"fantasy": {"command": "uv",
  "args": ["run", "--directory", "/Users/jcarroll/Repositories/fantasy-mcp", "fantasy-mcp"]}}}
```

## Tools

- `whoami` — confirms auth; returns league name, season, your team.
- `get_my_team` — your record, points, and roster with lineup slots.

## Develop

`uv run pytest`
```

- [ ] **Step 6: Commit (verify `.env` is NOT staged)**

```bash
git add .mcp.json README.md
git status --short   # must NOT list .env
git commit -m "docs: add README and Claude Code MCP registration"
```

- [ ] **Step 7: Verify from Claude Code**

Restart `claude` in this directory, run `/mcp` to confirm `fantasy` is connected, then ask: "run whoami". Expected: your league and team name.
