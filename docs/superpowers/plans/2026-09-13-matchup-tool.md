# `get_matchup` Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `get_matchup` MCP tool returning the user's current-week head-to-head matchup (both teams' live score, projection, win probability, and every rostered player with actual/projected points), and move payload shaping out of `server.py` into `shapes.py`.

**Architecture:** `shapes.py` holds pure `dict -> dict` functions (the existing `team_by_id`/`shape_whoami`/`shape_team` helpers moved verbatim, plus new `find_matchup`/`shape_matchup`). `server.py` keeps only FastMCP plumbing and thin tools. `EspnClient` is unchanged; the new tool requests `mMatchup`, `mMatchupScore`, `mTeam` in one call.

**Tech Stack:** Python 3.12, uv, fastmcp 4.0.3, httpx; pytest + respx.

**Spec:** `docs/superpowers/specs/2026-09-13-matchup-tool-design.md`

---

## File structure

| File | Responsibility |
|------|----------------|
| `src/fantasy_mcp/shapes.py` | NEW — all ESPN-JSON → tool-output shaping |
| `src/fantasy_mcp/server.py` | FastMCP app, INSTRUCTIONS, tools only |
| `tests/test_shapes.py` | NEW — shaping unit tests (moved + new) |
| `tests/test_server.py` | tool tests only |
| `tests/fixtures/matchup.json` | NEW — trimmed, scrubbed real `mMatchup+mMatchupScore+mTeam` |
| `tests/conftest.py` | add `matchup_json` fixture |
| `README.md` | document the new tool |

Notes for the engineer:
- Run everything via `uv run ...`. Current state: 26 tests pass on branch `feat/matchup`.
- Commit messages follow Conventional Commits and end with the two trailer lines the controller gives you.
- `tests/fixtures/matchup.json` already exists on disk (untracked) — Task 2 commits it. Do not regenerate it.

---

### Task 1: Move shaping helpers to `shapes.py`

Pure refactor. Behavior and test assertions unchanged; only import paths move.

**Files:**
- Create: `src/fantasy_mcp/shapes.py`
- Modify: `src/fantasy_mcp/server.py`
- Create: `tests/test_shapes.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Create `src/fantasy_mcp/shapes.py`** with exactly this content (the five functions are moved verbatim from `server.py` lines 52–106):

```python
"""Pure functions that shape ESPN league JSON into tool output."""

from __future__ import annotations

from typing import Any

from fantasy_mcp import ids
from fantasy_mcp.config import Settings
from fantasy_mcp.espn import EspnError


def team_by_id(league: dict[str, Any], team_id: int) -> dict[str, Any]:
    for team in league.get("teams", []):
        if team.get("id") == team_id:
            return team
    raise EspnError(
        f"Team id {team_id} is not in this league. Check ESPN_TEAM_ID "
        "(or unset it to auto-detect your team)."
    )


def shape_whoami(league: dict[str, Any], team_id: int, settings: Settings) -> dict[str, Any]:
    team = team_by_id(league, team_id)
    return {
        "league_id": settings.league_id,
        "season": settings.season,
        "league_name": league.get("settings", {}).get("name"),
        "team_id": team_id,
        "team_name": team.get("name"),
    }


def _shape_player(entry: dict[str, Any]) -> dict[str, Any]:
    player = entry.get("playerPoolEntry", {}).get("player", {})
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
```

- [ ] **Step 2: Edit `src/fantasy_mcp/server.py`**

Delete everything from the line `# --- shaping ---...` through the end of `shape_team` (the block that ends with `"roster": [_shape_player(e) for e in entries],\n    }` — lines 49–106 of the current file). Then change the imports at the top from:

```python
from fantasy_mcp import ids
from fantasy_mcp.config import ConfigError, Settings, load_settings
from fantasy_mcp.espn import EspnClient, EspnError
```
to:
```python
from fantasy_mcp.config import ConfigError, load_settings
from fantasy_mcp.espn import EspnClient, EspnError
from fantasy_mcp.shapes import shape_team, shape_whoami, team_by_id
```

The `# --- tools ---` section and everything below it stay exactly as they are.

- [ ] **Step 3: Create `tests/test_shapes.py`** by moving the four shaping tests out of `tests/test_server.py`:

```python
import pytest

from fantasy_mcp import shapes
from fantasy_mcp.espn import EspnError


def test_shape_team_orders_starters_first_and_maps_ids(league_json):
    team = league_json["teams"][0]
    shaped = shapes.shape_team(team)

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


def test_shape_team_tolerates_entry_without_player(league_json):
    team = league_json["teams"][0]
    team["roster"]["entries"].append({"lineupSlotId": 21})
    shaped = shapes.shape_team(team)
    ir_row = shaped["roster"][-1]
    assert ir_row["slot"] == "IR"
    assert ir_row["name"] is None
    assert ir_row["position"] == "UNKNOWN_-1"


def test_shape_whoami(league_json, settings):
    out = shapes.shape_whoami(league_json, team_id=3, settings=settings)
    assert out == {
        "league_id": 4242,
        "season": 2026,
        "league_name": "Test League",
        "team_id": 3,
        "team_name": "My Squad",
    }


def test_team_by_id_missing_raises(league_json):
    with pytest.raises(EspnError, match="ESPN_TEAM_ID"):
        shapes.team_by_id(league_json, 42)
```

- [ ] **Step 4: Edit `tests/test_server.py`** — delete the four functions `test_shape_team_orders_starters_first_and_maps_ids`, `test_shape_team_tolerates_entry_without_player`, `test_shape_whoami`, `test_team_by_id_missing_raises` (current lines 22–71). Keep the imports, the `client` fixture, and the four tool tests. The file should now contain exactly: imports, `client` fixture, `test_whoami_tool`, `test_get_my_team_tool`, `test_tool_surfaces_auth_error`, `test_tool_surfaces_bad_configured_team_id`.

- [ ] **Step 5: Run the suite**

Run: `uv run pytest -q`
Expected: `26 passed` (same count — tests moved, not added). Also: `uv run python -c "import fantasy_mcp.server as s; print(sorted(n for n in dir(s) if n.startswith('shape')))"` → `[]` (no shaping functions left in server).

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_mcp/shapes.py src/fantasy_mcp/server.py tests/test_shapes.py tests/test_server.py
git commit -m "refactor: move payload shaping into shapes module"
```

---

### Task 2: Commit the matchup fixture and add a conftest fixture

**Files:**
- Add (already on disk, untracked): `tests/fixtures/matchup.json`
- Modify: `tests/conftest.py`

The fixture is a trimmed real response (league/team/player names scrubbed). Key facts you will assert against later:
- `scoringPeriodId: 1`, `status.currentMatchupPeriod: 1`
- `teams`: id 12 "My Matchup Team"/"MMT" (owner `{ABC-123}` = our settings SWID), id 11 "Opponent Team"/"OPP"
- `schedule[0]`: period 1, `winner: "UNDECIDED"`, home = team 12 (`totalPointsLive 73.3`, `totalProjectedPointsLive 136.59`, `winProbability 0.76`), away = team 11 (`58.52`, `106.41`, `0.24`). Each side has 4 roster entries in file order BENCH(20), starter(2), IR(21), starter(4).
- `schedule[1]`: period 2 between teams 1 and 2 (team 12 has no game → bye path).

- [ ] **Step 1: Verify the fixture exists and parses**

Run: `uv run python -c "import json; d=json.load(open('tests/fixtures/matchup.json')); print(d['scoringPeriodId'], [g['matchupPeriodId'] for g in d['schedule']], [t['id'] for t in d['teams']])"`
Expected: `1 [1, 2] [12, 11]`

If the file is missing, STOP and report BLOCKED — do not fabricate it.

- [ ] **Step 2: Add the fixture to `tests/conftest.py`** — append at the end:

```python
@pytest.fixture
def matchup_json() -> dict:
    return json.loads((FIXTURES / "matchup.json").read_text())
```

- [ ] **Step 3: Run the suite**

Run: `uv run pytest -q`
Expected: `26 passed`

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/matchup.json tests/conftest.py
git commit -m "test: add scrubbed ESPN matchup fixture"
```

---

### Task 3: `find_matchup`

**Files:**
- Modify: `src/fantasy_mcp/shapes.py`
- Modify: `tests/test_shapes.py`

- [ ] **Step 1: Append failing tests to `tests/test_shapes.py`**

```python
def test_find_matchup_returns_game_containing_team(matchup_json):
    game = shapes.find_matchup(matchup_json, team_id=12, period=1)
    assert game["id"] == 6
    assert game["home"]["teamId"] == 12


def test_find_matchup_matches_away_side_too(matchup_json):
    game = shapes.find_matchup(matchup_json, team_id=11, period=1)
    assert game["id"] == 6


def test_find_matchup_bye_week_raises(matchup_json):
    with pytest.raises(EspnError, match="week 2"):
        shapes.find_matchup(matchup_json, team_id=12, period=2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_shapes.py -v -k find_matchup`
Expected: 3 FAIL with `AttributeError: module 'fantasy_mcp.shapes' has no attribute 'find_matchup'`

- [ ] **Step 3: Add `find_matchup` to `src/fantasy_mcp/shapes.py`** (after `shape_team`):

```python
def find_matchup(league: dict[str, Any], team_id: int, period: int) -> dict[str, Any]:
    """Return the schedule entry for ``period`` in which ``team_id`` plays."""
    for game in league.get("schedule", []):
        if game.get("matchupPeriodId") != period:
            continue
        sides = (game.get("home", {}).get("teamId"), game.get("away", {}).get("teamId"))
        if team_id in sides:
            return game
    raise EspnError(f"No matchup for your team in week {period} (bye week?).")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: `29 passed`

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/shapes.py tests/test_shapes.py
git commit -m "feat: locate the user's matchup for a given week"
```

---

### Task 4: `shape_matchup`

**Files:**
- Modify: `src/fantasy_mcp/shapes.py`
- Modify: `tests/test_shapes.py`

- [ ] **Step 1: Append failing tests to `tests/test_shapes.py`**

```python
def test_shape_matchup_full_shape(matchup_json):
    game = matchup_json["schedule"][0]
    out = shapes.shape_matchup(game, matchup_json, my_team_id=12)

    assert out["week"] == 1
    assert out["status"] == "IN_PROGRESS"
    assert out["is_home"] is True

    me = out["my_team"]
    assert {k: me[k] for k in ("team_id", "name", "abbrev", "score", "projected", "win_probability")} == {
        "team_id": 12,
        "name": "My Matchup Team",
        "abbrev": "MMT",
        "score": 73.3,
        "projected": 136.59,
        "win_probability": 0.76,
    }
    # Starters first (by slot id), then bench, then IR — regardless of file order.
    assert [p["name"] for p in me["roster"]] == [
        "Home Starter One",
        "Home Starter NoStats",
        "Home Bench Guy",
        "Home IR Guy",
    ]
    assert me["roster"][0] == {
        "name": "Home Starter One",
        "position": "RB",
        "slot": "RB",
        "pro_team": "IND",
        "injury_status": "ACTIVE",
        "points": 18.5,
        "projected": 17.77,
    }
    # No stats[] on the player -> projected is None, points still present.
    assert me["roster"][1]["points"] == 7.0
    assert me["roster"][1]["projected"] is None
    assert me["roster"][3]["slot"] == "IR"
    assert me["roster"][3]["projected"] == 9.73

    opp = out["opponent"]
    assert opp["team_id"] == 11
    assert opp["name"] == "Opponent Team"
    assert opp["score"] == 58.52
    assert opp["projected"] == 106.41
    assert opp["win_probability"] == 0.24
    assert [p["name"] for p in opp["roster"]] == [
        "Away Starter One",
        "Away Starter NoStats",
        "Away Bench Guy",
        "Away IR Guy",
    ]
    assert opp["roster"][0]["projected"] == 18.52


def test_shape_matchup_from_away_perspective(matchup_json):
    game = matchup_json["schedule"][0]
    out = shapes.shape_matchup(game, matchup_json, my_team_id=11)
    assert out["is_home"] is False
    assert out["my_team"]["team_id"] == 11
    assert out["opponent"]["team_id"] == 12


def test_shape_matchup_final_status(matchup_json):
    game = matchup_json["schedule"][0]
    game["winner"] = "AWAY"
    out = shapes.shape_matchup(game, matchup_json, my_team_id=12)
    assert out["status"] == "FINAL"


def test_shape_matchup_upcoming_when_no_points(matchup_json):
    game = matchup_json["schedule"][0]
    for side in ("home", "away"):
        game[side]["totalPointsLive"] = 0.0
        game[side]["totalPoints"] = 0.0
    out = shapes.shape_matchup(game, matchup_json, my_team_id=12)
    assert out["status"] == "UPCOMING"


def test_shape_matchup_falls_back_to_total_points_and_null_projection(matchup_json):
    game = matchup_json["schedule"][0]
    for key in ("totalPointsLive", "totalProjectedPoints", "totalProjectedPointsLive", "winProbability"):
        game["home"].pop(key)
    game["home"]["totalPoints"] = 101.234
    out = shapes.shape_matchup(game, matchup_json, my_team_id=12)
    assert out["my_team"]["score"] == 101.23
    assert out["my_team"]["projected"] is None
    assert out["my_team"]["win_probability"] is None


def test_shape_matchup_unknown_opponent_and_missing_roster(matchup_json):
    game = matchup_json["schedule"][0]
    game["away"]["teamId"] = 77
    del game["away"]["rosterForCurrentScoringPeriod"]
    out = shapes.shape_matchup(game, matchup_json, my_team_id=12)
    assert out["opponent"]["team_id"] == 77
    assert out["opponent"]["name"] is None
    assert out["opponent"]["abbrev"] is None
    assert out["opponent"]["roster"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_shapes.py -v -k shape_matchup`
Expected: 6 FAIL with `AttributeError: module 'fantasy_mcp.shapes' has no attribute 'shape_matchup'`

- [ ] **Step 3: Add `shape_matchup` and helpers to `src/fantasy_mcp/shapes.py`** (after `find_matchup`):

```python
PROJECTION_SOURCE_ID = 1  # player.stats[].statSourceId: 1 = projected, 0 = actual


def _round(value: Any) -> float | None:
    return None if value is None else round(float(value), 2)


def _projected_points(player: dict[str, Any], scoring_period: int) -> float | None:
    for stat in player.get("stats", []):
        if (
            stat.get("statSourceId") == PROJECTION_SOURCE_ID
            and stat.get("scoringPeriodId") == scoring_period
        ):
            return _round(stat.get("appliedTotal"))
    return None


def _shape_matchup_player(entry: dict[str, Any], scoring_period: int) -> dict[str, Any]:
    pool_entry = entry.get("playerPoolEntry", {})
    row = _shape_player(entry)
    row["points"] = _round(pool_entry.get("appliedStatTotal", 0.0))
    row["projected"] = _projected_points(pool_entry.get("player", {}), scoring_period)
    return row


def _side_score(side: dict[str, Any]) -> float:
    live = side.get("totalPointsLive")
    return _round(live if live is not None else side.get("totalPoints", 0.0))


def _shape_side(side: dict[str, Any], league: dict[str, Any]) -> dict[str, Any]:
    team_id = side.get("teamId")
    team = next((t for t in league.get("teams", []) if t.get("id") == team_id), {})
    projected = side.get("totalProjectedPointsLive", side.get("totalProjectedPoints"))
    entries = sorted(
        side.get("rosterForCurrentScoringPeriod", {}).get("entries", []), key=_slot_sort_key
    )
    scoring_period = league.get("scoringPeriodId", -1)
    return {
        "team_id": team_id,
        "name": team.get("name"),
        "abbrev": team.get("abbrev"),
        "score": _side_score(side),
        "projected": _round(projected),
        "win_probability": side.get("winProbability"),
        "roster": [_shape_matchup_player(e, scoring_period) for e in entries],
    }


def _matchup_status(game: dict[str, Any]) -> str:
    if game.get("winner") in ("HOME", "AWAY", "TIE"):
        return "FINAL"
    if _side_score(game.get("home", {})) > 0 or _side_score(game.get("away", {})) > 0:
        return "IN_PROGRESS"
    return "UPCOMING"


def shape_matchup(game: dict[str, Any], league: dict[str, Any], my_team_id: int) -> dict[str, Any]:
    home, away = game.get("home", {}), game.get("away", {})
    is_home = home.get("teamId") == my_team_id
    mine, theirs = (home, away) if is_home else (away, home)
    return {
        "week": game.get("matchupPeriodId"),
        "status": _matchup_status(game),
        "is_home": is_home,
        "my_team": _shape_side(mine, league),
        "opponent": _shape_side(theirs, league),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: `35 passed`

Troubleshooting: if the roster order test fails, check `_slot_sort_key` — slot 2 (RB) and 4 (WR) are bucket 0, BENCH (20) bucket 1, IR (21) bucket 2; the fixture lists them BENCH, 2, 21, 4 on purpose.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/shapes.py tests/test_shapes.py
git commit -m "feat: shape a head-to-head matchup with per-player points"
```

---

### Task 5: `get_matchup` tool, instructions, README

**Files:**
- Modify: `src/fantasy_mcp/server.py`
- Modify: `tests/test_server.py`
- Modify: `README.md`

- [ ] **Step 1: Append failing tests to `tests/test_server.py`**

```python
@respx.mock
async def test_get_matchup_tool(client, matchup_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=matchup_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_matchup", {})
    assert result.data["week"] == 1
    assert result.data["my_team"]["team_id"] == 12
    assert result.data["opponent"]["team_id"] == 11
    assert len(result.data["my_team"]["roster"]) == 4
    views = route.calls.last.request.url.params.get_list("view")
    assert views == ["mMatchup", "mMatchupScore", "mTeam"]


@respx.mock
async def test_get_matchup_tool_bye_week_is_tool_error(client, matchup_json):
    matchup_json["status"]["currentMatchupPeriod"] = 2
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=matchup_json))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="week 2"):
            await c.call_tool("get_matchup", {})
```

Note: the `client` fixture uses `settings` with `team_id=None` and `swid="{ABC-123}"`; the matchup fixture's team 12 owner is `{ABC-123}`, so auto-detection resolves to 12.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_server.py -v -k get_matchup`
Expected: 2 FAIL — the `ToolError`/error mentions `Unknown tool: get_matchup` (exact wording may vary; the point is the tool doesn't exist).

- [ ] **Step 3: Add the tool to `src/fantasy_mcp/server.py`**

Change the shapes import to:
```python
from fantasy_mcp.shapes import find_matchup, shape_matchup, shape_team, shape_whoami, team_by_id
```

Add after `get_my_team` (before `def main()`):

```python
@mcp.tool
def get_matchup() -> dict[str, Any]:
    """Return the user's current-week head-to-head matchup with live scoring.

    Use this for "am I winning?", "who am I playing?", "who's left to play?",
    or "should I have started X?". Covers the current week only.

    Top level: week; status (UPCOMING, IN_PROGRESS, or FINAL); is_home; my_team;
    opponent. Each team has: team_id, name, abbrev, score (fantasy points so far
    this week), projected (ESPN's live projection for the week's final score),
    win_probability (0-1, may be null), and roster. Each roster row has the same
    fields as get_my_team (name, position, slot, pro_team, injury_status) plus
    points (scored so far this week) and projected (ESPN's projection for this
    player this week; null if unavailable). Only rows whose slot is not BENCH or IR
    count toward score.
    """
    try:
        client = _get_client()
        league = client.get("mMatchup", "mMatchupScore", "mTeam")
        team_id = client.find_my_team_id(league)
        week = league.get("status", {}).get("currentMatchupPeriod")
        game = find_matchup(league, team_id, week)
        return shape_matchup(game, league, team_id)
    except (EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e
```

- [ ] **Step 4: Update `INSTRUCTIONS` in `src/fantasy_mcp/server.py`**

Replace the paragraph:
```
Only whoami and get_my_team exist. There is no matchup, standings, free agent,
or transaction data yet -- say so instead of inventing it.
```
with:
```
Use get_matchup for anything about this week's game: score, projection, win
probability, opponent, or who has played. Only whoami, get_my_team, and
get_matchup exist. There is no standings, free agent, transaction, or
past-week data yet -- say so instead of inventing it.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: `37 passed`

Also confirm registration: `uv run python -c "
import asyncio
from fastmcp import Client
from fantasy_mcp import server
async def m():
    async with Client(server.mcp) as c:
        print(sorted(t.name for t in await c.list_tools()))
asyncio.run(m())"` → `['get_matchup', 'get_my_team', 'whoami']`

- [ ] **Step 6: Update `README.md`** — in the `## Tools` list, add after the `get_my_team` line:

```markdown
- `get_matchup` — this week's head-to-head: live score, projection, win
  probability, and both rosters with per-player actual/projected points.
```

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_mcp/server.py tests/test_server.py README.md
git commit -m "feat: add get_matchup tool for the current week's head-to-head"
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
        m = (await c.call_tool("get_matchup", {})).data
    print(m["week"], m["status"], "home" if m["is_home"] else "away")
    for side in ("my_team", "opponent"):
        t = m[side]
        print(f'\n{t["name"]} ({t["abbrev"]})  score={t["score"]} proj={t["projected"]} wp={t["win_probability"]}')
        for p in t["roster"]:
            print(f'  {p["slot"]:<6} {p["position"]:<5} {str(p["name"]):<24} {p["pro_team"]:<4} {str(p["points"]):>6} / {p["projected"]}')
asyncio.run(main())
EOF
```

Expected: week 1, IN_PROGRESS or FINAL, both rosters populated, no `UNKNOWN_` ids, no exceptions. Any `UNKNOWN_<n>` → add to `ids.py` and commit `fix: map ESPN id <n>`.

- [ ] **Step 2: Verify from Claude Code** — restart `claude` in the repo, run `/mcp`, ask "am I winning my matchup?".
