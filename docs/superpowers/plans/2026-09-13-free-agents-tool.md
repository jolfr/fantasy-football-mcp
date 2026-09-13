# `get_free_agents` Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `get_free_agents(position, limit, sort)` MCP tool that lists available players (free agents + waivers) with ownership, projection, and rank data.

**Architecture:** New pure module `filters.py` builds the ESPN `X-Fantasy-Filter` payload (request side, validates arguments). `shapes.py` gains `shape_free_agent` and a generalized `_stat` helper shared with matchup shaping (response side). `server.py` adds one thin tool that requests `kona_player_info` + `mStatus` in a single call.

**Tech Stack:** Python 3.12, uv, fastmcp 4.0.3, httpx; pytest + respx.

**Spec:** `docs/superpowers/specs/2026-09-13-free-agents-tool-design.md`

---

## File structure

| File | Responsibility |
|------|----------------|
| `src/fantasy_mcp/filters.py` | NEW — `X-Fantasy-Filter` builders + argument validation; imports nothing from the package |
| `src/fantasy_mcp/shapes.py` | + `_stat`, constants, `shape_free_agent` |
| `src/fantasy_mcp/server.py` | + `get_free_agents` tool, INSTRUCTIONS update |
| `tests/test_filters.py` | NEW |
| `tests/test_shapes.py` | + free-agent shaping tests |
| `tests/test_server.py` | + tool tests |
| `tests/fixtures/free_agents.json` | NEW — trimmed real `kona_player_info`+`mStatus` (already on disk, untracked) |
| `tests/conftest.py` | + `free_agents_json` fixture |
| `README.md` | + tool bullet |

Notes for the engineer:
- Run everything via `uv run ...`. Current state: 40 tests pass on branch `feat/free-agents`.
- Commit messages: Conventional Commits, ending with the two trailer lines the controller gives you.
- `tests/fixtures/free_agents.json` already exists (untracked). Task 2 commits it. Don't regenerate it.

---

### Task 1: `filters.py` — build the free-agent filter

**Files:**
- Create: `src/fantasy_mcp/filters.py`
- Create: `tests/test_filters.py`

- [ ] **Step 1: Write the failing tests** — `tests/test_filters.py`:

```python
import pytest

from fantasy_mcp.filters import MAX_LIMIT, POSITION_SLOTS, SORTS, free_agent_filter

STATUS = {"value": ["FREEAGENT", "WAIVERS"]}


def test_default_filter_sorts_by_percent_owned_with_no_position():
    out = free_agent_filter(season=2026, position=None, limit=10, sort="owned")
    assert out == {
        "players": {
            "filterStatus": STATUS,
            "limit": 10,
            "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
        }
    }


def test_position_is_case_insensitive_and_maps_to_slot():
    out = free_agent_filter(season=2026, position="rb", limit=5, sort="owned")
    assert out["players"]["filterSlotIds"] == {"value": [2]}
    assert out["players"]["limit"] == 5


def test_defense_position_maps_to_slot_16():
    out = free_agent_filter(season=2026, position="D_ST", limit=5, sort="owned")
    assert out["players"]["filterSlotIds"] == {"value": [16]}


def test_projected_sort_uses_season_stat_id():
    out = free_agent_filter(season=2026, position=None, limit=10, sort="projected")
    assert out["players"]["sortAppliedStatTotal"] == {
        "sortPriority": 1,
        "sortAsc": False,
        "value": "102026",
    }
    assert "sortPercOwned" not in out["players"]


def test_invalid_position_lists_valid_values():
    with pytest.raises(ValueError, match="position must be one of") as exc:
        free_agent_filter(season=2026, position="FLEX", limit=10, sort="owned")
    for name in POSITION_SLOTS:
        assert name in str(exc.value)
    assert "FLEX" in str(exc.value)


def test_invalid_sort_lists_valid_values():
    with pytest.raises(ValueError, match="sort must be one of") as exc:
        free_agent_filter(season=2026, position=None, limit=10, sort="points")
    for name in SORTS:
        assert name in str(exc.value)


@pytest.mark.parametrize("limit", [0, MAX_LIMIT + 1, -3])
def test_limit_out_of_range(limit):
    with pytest.raises(ValueError, match=f"limit must be between 1 and {MAX_LIMIT}"):
        free_agent_filter(season=2026, position=None, limit=limit, sort="owned")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_filters.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_mcp.filters'`

- [ ] **Step 3: Implement `src/fantasy_mcp/filters.py`**

```python
"""Builders for ESPN's X-Fantasy-Filter request header."""

from __future__ import annotations

from typing import Any

# Fantasy position name -> lineupSlotId used by ESPN's filterSlotIds.
POSITION_SLOTS: dict[str, int] = {
    "QB": 0,
    "RB": 2,
    "WR": 4,
    "TE": 6,
    "K": 17,
    "D_ST": 16,
}
SORTS = ("owned", "projected")
MAX_LIMIT = 50

_AVAILABLE = {"value": ["FREEAGENT", "WAIVERS"]}


def free_agent_filter(
    *, season: int, position: str | None, limit: int, sort: str
) -> dict[str, Any]:
    """Filter for available players, optionally by position, sorted by ownership or projection."""
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT} (got {limit}).")
    if sort not in SORTS:
        raise ValueError(f"sort must be one of {', '.join(SORTS)} (got {sort!r}).")

    players: dict[str, Any] = {"filterStatus": _AVAILABLE, "limit": limit}

    if position is not None:
        slot = POSITION_SLOTS.get(position.upper())
        if slot is None:
            raise ValueError(
                f"position must be one of {', '.join(POSITION_SLOTS)} (got {position!r})."
            )
        players["filterSlotIds"] = {"value": [slot]}

    if sort == "projected":
        # ESPN stat id "10<season>" is the season-long projected total.
        players["sortAppliedStatTotal"] = {
            "sortPriority": 1,
            "sortAsc": False,
            "value": f"10{season}",
        }
    else:
        players["sortPercOwned"] = {"sortPriority": 1, "sortAsc": False}

    return {"players": players}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: `49 passed` (40 + 9: seven functions, one parametrized ×3)

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/filters.py tests/test_filters.py
git commit -m "feat: build X-Fantasy-Filter for available players"
```

---

### Task 2: Fixture + conftest

**Files:**
- Add (already on disk, untracked): `tests/fixtures/free_agents.json`
- Modify: `tests/conftest.py`

Fixture facts: `scoringPeriodId: 1`, `seasonId: 2026`, two `players[]` entries:
1. `status "WAIVERS"`, `ratings["0"].positionalRanking 38`, player "Waiver Back" (RB, proTeamId 25 = SF, ACTIVE), `ownership {percentOwned 15.42, percentChange -0.03, percentStarted 0.22}`, `stats`: (period 1, source 0, 8.0), (period 1, source 1, 4.5), (period 0, source 0, 8.0), (period 0, source 1, 113.78).
2. `status "FREEAGENT"`, no `ratings`, player "Sparse Receiver" (WR, proTeamId 22 = ARI, QUESTIONABLE), no `ownership`, no `stats`.

- [ ] **Step 1: Verify the fixture**

Run: `uv run python -c "import json; d=json.load(open('tests/fixtures/free_agents.json')); print(d['scoringPeriodId'], [p['status'] for p in d['players']], d['players'][0]['ratings']['0']['positionalRanking'])"`
Expected: `1 ['WAIVERS', 'FREEAGENT'] 38`. If the file is missing, STOP — report BLOCKED.

- [ ] **Step 2: Append to `tests/conftest.py`**

```python


@pytest.fixture
def free_agents_json() -> dict:
    return json.loads((FIXTURES / "free_agents.json").read_text())
```

- [ ] **Step 3: Verify** — `uv run pytest -q` → `49 passed`

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/free_agents.json tests/conftest.py
git commit -m "test: add scrubbed ESPN free-agent fixture"
```

---

### Task 3: Generalize the stat lookup in `shapes.py`

Pure refactor: `_projected_points` becomes a thin wrapper over a new `_stat`. No test changes; all 49 must still pass.

**Files:**
- Modify: `src/fantasy_mcp/shapes.py`

- [ ] **Step 1: Replace the constant and `_projected_points`**

Change the constant block near the top of `src/fantasy_mcp/shapes.py` from:
```python
PROJECTION_SOURCE_ID = 1  # player.stats[].statSourceId: 1 = projected, 0 = actual
```
to:
```python
# player.stats[] items are keyed by scoringPeriodId (0 = season total, N = week N)
# and statSourceId (0 = actual, 1 = projected).
SEASON_PERIOD = 0
ACTUAL_SOURCE_ID = 0
PROJECTION_SOURCE_ID = 1
```

Replace the whole `_projected_points` function with:
```python
def _stat(player: dict[str, Any], *, period: int, source: int) -> float | None:
    """appliedTotal of the stats[] item for ``period``/``source``, rounded; None if absent."""
    for stat in player.get("stats") or []:
        if stat.get("scoringPeriodId") == period and stat.get("statSourceId") == source:
            return _round(stat.get("appliedTotal"))
    return None


def _projected_points(player: dict[str, Any], scoring_period: int) -> float | None:
    return _stat(player, period=scoring_period, source=PROJECTION_SOURCE_ID)
```

- [ ] **Step 2: Verify** — `uv run pytest -q` → `49 passed`

- [ ] **Step 3: Commit**

```bash
git add src/fantasy_mcp/shapes.py
git commit -m "refactor: generalize player stat lookup"
```

---

### Task 4: `shape_free_agent`

**Files:**
- Modify: `src/fantasy_mcp/shapes.py`
- Modify: `tests/test_shapes.py`

- [ ] **Step 1: Append failing tests to `tests/test_shapes.py`**

```python
def test_shape_free_agent_full_entry(free_agents_json):
    entry = free_agents_json["players"][0]
    out = shapes.shape_free_agent(entry, scoring_period=1)
    assert out == {
        "name": "Waiver Back",
        "position": "RB",
        "pro_team": "SF",
        "injury_status": "ACTIVE",
        "status": "WAIVERS",
        "percent_owned": 15.4,
        "percent_change": -0.03,
        "season_projected": 113.78,
        "season_points": 8.0,
        "week_projected": 4.5,
        "week_points": 8.0,
        "positional_rank": 38,
    }


def test_shape_free_agent_sparse_entry_yields_nulls(free_agents_json):
    entry = free_agents_json["players"][1]
    out = shapes.shape_free_agent(entry, scoring_period=1)
    assert out["name"] == "Sparse Receiver"
    assert out["position"] == "WR"
    assert out["pro_team"] == "ARI"
    assert out["injury_status"] == "QUESTIONABLE"
    assert out["status"] == "FREEAGENT"
    for key in (
        "percent_owned",
        "percent_change",
        "season_projected",
        "season_points",
        "week_projected",
        "week_points",
        "positional_rank",
    ):
        assert out[key] is None, key


def test_shape_free_agent_tolerates_missing_player():
    out = shapes.shape_free_agent({"status": "FREEAGENT"}, scoring_period=1)
    assert out["name"] is None
    assert out["position"] == "UNKNOWN_-1"
    assert out["status"] == "FREEAGENT"
    assert out["season_projected"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_shapes.py -v -k free_agent`
Expected: 3 FAIL with `AttributeError: module 'fantasy_mcp.shapes' has no attribute 'shape_free_agent'`

- [ ] **Step 3: Add to `src/fantasy_mcp/shapes.py`** (at the end of the file):

```python
def _round1(value: Any) -> float | None:
    return None if value is None else round(float(value), 1)


def shape_free_agent(entry: dict[str, Any], scoring_period: int) -> dict[str, Any]:
    """Shape one kona_player_info players[] entry for the free-agent list."""
    player = entry.get("player") or {}
    ownership = player.get("ownership") or {}
    season_rating = (entry.get("ratings") or {}).get("0") or {}
    return {
        "name": player.get("fullName"),
        "position": ids.name(ids.POSITIONS, player.get("defaultPositionId", -1)),
        "pro_team": ids.name(ids.PRO_TEAMS, player.get("proTeamId", -1)),
        "injury_status": player.get("injuryStatus"),
        "status": entry.get("status"),
        "percent_owned": _round1(ownership.get("percentOwned")),
        "percent_change": _round(ownership.get("percentChange")),
        "season_projected": _stat(player, period=SEASON_PERIOD, source=PROJECTION_SOURCE_ID),
        "season_points": _stat(player, period=SEASON_PERIOD, source=ACTUAL_SOURCE_ID),
        "week_projected": _stat(player, period=scoring_period, source=PROJECTION_SOURCE_ID),
        "week_points": _stat(player, period=scoring_period, source=ACTUAL_SOURCE_ID),
        "positional_rank": season_rating.get("positionalRanking"),
    }
```

- [ ] **Step 4: Verify** — `uv run pytest -q` → `52 passed`

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/shapes.py tests/test_shapes.py
git commit -m "feat: shape free-agent entries with ownership and projections"
```

---

### Task 5: `get_free_agents` tool, instructions, README

**Files:**
- Modify: `src/fantasy_mcp/server.py`
- Modify: `tests/test_server.py`
- Modify: `README.md`

- [ ] **Step 1: Append failing tests to `tests/test_server.py`**

Add `import json` to the imports at the top of the file, then append:

```python
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
async def test_get_free_agents_invalid_position_is_tool_error(client):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="position must be one of"):
            await c.call_tool("get_free_agents", {"position": "FLEX"})
    assert not route.called
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_server.py -v -k free_agents`
Expected: 3 FAIL (unknown tool `get_free_agents`).

- [ ] **Step 3: Add the tool to `src/fantasy_mcp/server.py`**

Add import (after the `espn` import line):
```python
from fantasy_mcp.filters import free_agent_filter
```
Change the shapes import to:
```python
from fantasy_mcp.shapes import (
    find_matchup,
    shape_free_agent,
    shape_matchup,
    shape_team,
    shape_whoami,
    team_by_id,
)
```

Add after `get_matchup` (before `def main()`):

```python
@mcp.tool
def get_free_agents(
    position: str | None = None,
    limit: int = 10,
    sort: str = "owned",
) -> dict[str, Any]:
    """List available players (free agents and waiver claims) in the user's league.

    Use this for "who should I pick up?", "best available RB", or "who's trending".

    Args: position -- one of QB, RB, WR, TE, K, D_ST (case-insensitive); omit for
    all positions. limit -- 1 to 50, default 10. sort -- "owned" (most rostered
    across ESPN first, default) or "projected" (highest season projection first).

    Each player row: name, position, pro_team, injury_status, status (FREEAGENT =
    add immediately; WAIVERS = must submit a claim), percent_owned (% of ESPN
    leagues rostering them), percent_change (ownership trend -- positive means
    being picked up), season_projected / season_points (full-season projected /
    scored so far), week_projected / week_points (current NFL week), and
    positional_rank (ESPN's season rank at their position; null if unavailable).
    Next-week projections are not available from this tool.
    """
    try:
        client = _get_client()
        fantasy_filter = free_agent_filter(
            season=client.settings.season, position=position, limit=limit, sort=sort
        )
        league = client.get("kona_player_info", "mStatus", fantasy_filter=fantasy_filter)
        period = league.get("scoringPeriodId")
        players = [shape_free_agent(e, period) for e in league.get("players", [])]
        return {
            "week": period,
            "position": position.upper() if position else None,
            "sort": sort,
            "players": players,
        }
    except (ValueError, EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e
```

- [ ] **Step 4: Update `INSTRUCTIONS` in `server.py`**

Replace:
```
Use get_matchup for anything about this week's game: score, projection, win
probability, opponent, or per-player points. Only whoami, get_my_team, and
get_matchup exist. There is no standings, free agent, transaction, or
past-week data yet -- say so instead of inventing it.
```
with:
```
Use get_matchup for anything about this week's game: score, projection, win
probability, opponent, or per-player points. Use get_free_agents for pickup,
waiver, or "who's available" questions, and compare candidates against the
roster from get_my_team before recommending a move. Only whoami, get_my_team,
get_matchup, and get_free_agents exist. There is no standings, transaction,
or past-week data yet -- say so instead of inventing it.
```

- [ ] **Step 5: Verify**

Run: `uv run pytest -q` → `55 passed`
Registration: `uv run python -c "
import asyncio
from fastmcp import Client
from fantasy_mcp import server
async def m():
    async with Client(server.mcp) as c:
        print(sorted(t.name for t in await c.list_tools()))
asyncio.run(m())"` → `['get_free_agents', 'get_matchup', 'get_my_team', 'whoami']`

- [ ] **Step 6: Update `README.md`** — in `## Tools`, add after the `get_matchup` bullet:

```markdown
- `get_free_agents` — available players (free agents + waivers), optionally by
  position, sorted by % rostered or season projection, with ownership trend,
  projections, and positional rank.
```

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_mcp/server.py tests/test_server.py README.md
git commit -m "feat: add get_free_agents tool"
```

---

### Task 6: Live smoke test

Run by the controller (needs the user's `.env`). Not delegated.

- [ ] **Step 1: Call the tool against the real league**

```bash
uv run python - <<'EOF'
import asyncio
from fastmcp import Client
from fantasy_mcp import server
async def main():
    async with Client(server.mcp) as c:
        for args in ({"position": "RB"}, {"sort": "projected", "limit": 5}, {"position": "d_st", "limit": 3}):
            r = (await c.call_tool("get_free_agents", args)).data
            print(f'\n{args} -> week {r["week"]}, {len(r["players"])} players')
            for p in r["players"]:
                print(f'  {p["status"]:<9} {p["position"]:<4} {str(p["name"]):<24} {p["pro_team"]:<4} own={p["percent_owned"]} chg={p["percent_change"]} sproj={p["season_projected"]} wk={p["week_points"]}/{p["week_projected"]} rank={p["positional_rank"]} {p["injury_status"]}')
asyncio.run(main())
EOF
```

Expected: three lists, no exceptions, no `UNKNOWN_` ids, `status` only FREEAGENT/WAIVERS, positions matching the filter.

- [ ] **Step 2: Verify from Claude Code** — restart `claude`, run `/mcp`, ask "who's the best available RB I should pick up?".
