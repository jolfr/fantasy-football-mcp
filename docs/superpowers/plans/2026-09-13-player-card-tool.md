# `get_player` Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `get_player(name | player_id)` returning a full player profile with league ownership, season totals/projection, outlook, and a per-week game log with named stat lines; add `player_id` to existing roster/free-agent rows.

**Architecture:** `stats.py` (stat-id → name data) and `players.py` (name → id resolution) are new pure modules. `EspnClient` gains one league-independent request (`get_players_index`). `filters.py` gains `player_card_filter`. `shapes.py` gains `shape_player_card`. `server.py` adds the tool and an in-process cache of the player index.

**Tech Stack:** Python 3.12, uv, fastmcp 4.0.3, httpx; pytest + respx.

**Spec:** `docs/superpowers/specs/2026-09-13-player-card-tool-design.md`

---

## File structure

| File | Responsibility |
|------|----------------|
| `src/fantasy_mcp/stats.py` | NEW — `STAT_NAMES`, `shape_stat_line` |
| `src/fantasy_mcp/players.py` | NEW — `resolve_player(name, index)` |
| `src/fantasy_mcp/espn.py` | + `_request` helper, `get_players_index` |
| `src/fantasy_mcp/filters.py` | + `player_card_filter` |
| `src/fantasy_mcp/shapes.py` | + `player_id` on rows, `shape_player_card` |
| `src/fantasy_mcp/server.py` | + index cache, `get_player`, INSTRUCTIONS |
| `tests/test_stats.py`, `tests/test_players.py` | NEW |
| `tests/test_espn.py`, `test_filters.py`, `test_shapes.py`, `test_server.py` | extended |
| `tests/fixtures/player_card.json`, `players_index.json` | NEW (already on disk, untracked) |
| `tests/fixtures/mteam_mroster.json`, `matchup.json`, `free_agents.json` | + player ids |
| `tests/conftest.py` | + fixtures |
| `README.md` | + bullet |

Notes for the engineer:
- Run everything via `uv run ...`. Current state: 65 tests pass on branch `feat/player-card`.
- Commit messages: Conventional Commits + the two trailer lines the controller gives you. Never `git add -A` unless told; two fixture files are untracked until their task.

---

### Task 1: `stats.py`

**Files:**
- Create: `src/fantasy_mcp/stats.py`
- Create: `tests/test_stats.py`

- [ ] **Step 1: Write the failing tests** — `tests/test_stats.py`:

```python
from fantasy_mcp.stats import STAT_NAMES, shape_stat_line


def test_maps_known_ids_drops_unknown_and_zero():
    raw = {"23": 19.0, "24": 98.0, "25": 2.0, "41": 3.0, "999": 7.0, "72": 0.0}
    assert shape_stat_line(raw) == {"rush_att": 19, "rush_yds": 98, "rush_td": 2}


def test_integral_floats_become_ints_but_fractions_stay():
    assert shape_stat_line({"3": 163.0, "21": 53.13}) == {"pass_yds": 163}
    assert shape_stat_line({"24": 5.5}) == {"rush_yds": 5.5}


def test_none_and_empty():
    assert shape_stat_line(None) == {}
    assert shape_stat_line({}) == {}


def test_names_are_unique_snake_case():
    names = list(STAT_NAMES.values())
    assert len(names) == len(set(names))
    assert all(n == n.lower() and " " not in n for n in names)
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_stats.py -v` → `ModuleNotFoundError: No module named 'fantasy_mcp.stats'`

- [ ] **Step 3: Implement `src/fantasy_mcp/stats.py`**

```python
"""ESPN stat id -> name mapping for player game logs."""

from __future__ import annotations

from typing import Any

# Ids confirmed against live appliedStats (points / league scoring) and
# community documentation of ESPN's fantasy stat ids. Unlisted ids are dropped.
STAT_NAMES: dict[int, str] = {
    # passing
    0: "pass_att",
    1: "pass_comp",
    3: "pass_yds",
    4: "pass_td",
    19: "pass_2pt",
    20: "pass_int",
    # rushing
    23: "rush_att",
    24: "rush_yds",
    25: "rush_td",
    26: "rush_2pt",
    # receiving
    58: "targets",
    53: "receptions",
    42: "rec_yds",
    43: "rec_td",
    44: "rec_2pt",
    # misc
    68: "fumbles",
    72: "fumbles_lost",
    # kicking
    74: "fg_made_50_plus",
    77: "fg_made_40_49",
    80: "fg_made_under_40",
    83: "fg_made",
    84: "fg_att",
    85: "fg_missed",
    86: "xp_made",
    87: "xp_att",
    88: "xp_missed",
    # defense / special teams
    95: "dst_int",
    96: "dst_fumble_rec",
    97: "dst_blocked_kicks",
    98: "dst_safeties",
    99: "dst_sacks",
    93: "dst_blocked_kick_td",
    101: "dst_kick_return_td",
    102: "dst_punt_return_td",
    103: "dst_fumble_return_td",
    104: "dst_int_return_td",
    120: "dst_points_allowed",
    127: "dst_yards_allowed",
    # team context
    155: "team_win",
    156: "team_loss",
    210: "games_played",
}


def shape_stat_line(raw: dict[str, Any] | None) -> dict[str, float]:
    """Map ESPN ``{stat_id: value}`` to ``{name: value}``; drop unmapped ids and zeros."""
    line: dict[str, float] = {}
    for key, value in (raw or {}).items():
        try:
            name = STAT_NAMES[int(key)]
            number = float(value)
        except (KeyError, TypeError, ValueError):
            continue
        if number == 0:
            continue
        line[name] = int(number) if number.is_integer() else number
    return line
```

- [ ] **Step 4: Verify** — `uv run pytest -q` → `69 passed`

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/stats.py tests/test_stats.py
git commit -m "feat: add ESPN stat id names and stat-line shaping"
```

---

### Task 2: `players.py` name resolution

**Files:**
- Add (untracked, on disk): `tests/fixtures/players_index.json`
- Modify: `tests/conftest.py`
- Create: `src/fantasy_mcp/players.py`
- Create: `tests/test_players.py`

Fixture facts (`players_index.json`, a JSON list): Tre Tucker (WR, LV/13, id 4362628, 25% owned), Tucker Kraft (TE, GB/9, id 4572680, 80%), Justin Tucker (K, BAL/33, id 15683, 40%), A.J. Brown (WR, PHI/21, id 1001, 99%), Jonathan Taylor (RB, IND/11, id 4242335, 99.9%), Sam Smith ×2 (ids 2001, 2002).

- [ ] **Step 1: Verify fixture, add conftest fixture**

Run: `uv run python -c "import json; d=json.load(open('tests/fixtures/players_index.json')); print(len(d), [p['fullName'] for p in d][:3])"` → `7 ['Tre Tucker', 'Tucker Kraft', 'Justin Tucker']`. Missing → STOP, report BLOCKED.

Append to `tests/conftest.py`:
```python


@pytest.fixture
def players_index() -> list:
    return json.loads((FIXTURES / "players_index.json").read_text())
```

- [ ] **Step 2: Write the failing tests** — `tests/test_players.py`:

```python
import pytest

from fantasy_mcp.espn import EspnError
from fantasy_mcp.players import resolve_player


def test_exact_match(players_index):
    assert resolve_player("Jonathan Taylor", players_index) == 4242335


def test_casefold_and_punctuation_insensitive(players_index):
    assert resolve_player("a.j. brown", players_index) == 1001
    assert resolve_player("  AJ   BROWN ", players_index) == 1001


def test_unique_substring(players_index):
    assert resolve_player("kraft", players_index) == 4572680


def test_ambiguous_substring_lists_candidates_by_ownership(players_index):
    with pytest.raises(EspnError) as exc:
        resolve_player("tucker", players_index)
    msg = str(exc.value)
    assert "Tucker Kraft (TE, GB, id 4572680)" in msg
    assert "Justin Tucker (K, BAL, id 15683)" in msg
    assert "Tre Tucker (WR, LV, id 4362628)" in msg
    assert msg.index("Tucker Kraft") < msg.index("Justin Tucker") < msg.index("Tre Tucker")
    assert "player_id" in msg


def test_duplicate_exact_names_are_ambiguous(players_index):
    with pytest.raises(EspnError, match="id 2001") as exc:
        resolve_player("Sam Smith", players_index)
    assert "id 2002" in str(exc.value)


def test_no_match(players_index):
    with pytest.raises(EspnError, match="No active player matches 'Nobody Real'"):
        resolve_player("Nobody Real", players_index)
```

- [ ] **Step 3: Run to verify failure** — `uv run pytest tests/test_players.py -v` → `ModuleNotFoundError: No module named 'fantasy_mcp.players'`

- [ ] **Step 4: Implement `src/fantasy_mcp/players.py`**

```python
"""Resolve player names against ESPN's active-player index."""

from __future__ import annotations

import re
from typing import Any

from fantasy_mcp import ids
from fantasy_mcp.espn import EspnError

MAX_CANDIDATES = 8
_DROP = re.compile(r"[.'’]")
_SPACES = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _SPACES.sub(" ", _DROP.sub("", text)).strip().casefold()


def _describe(player: dict[str, Any]) -> str:
    pos = ids.name(ids.POSITIONS, player.get("defaultPositionId", -1))
    team = ids.name(ids.PRO_TEAMS, player.get("proTeamId", -1))
    return f"{player.get('fullName')} ({pos}, {team}, id {player.get('id')})"


def _owned(player: dict[str, Any]) -> float:
    return float((player.get("ownership") or {}).get("percentOwned") or 0.0)


def resolve_player(name: str, index: list[dict[str, Any]]) -> int:
    """Return the ESPN player id for ``name``; raise EspnError if none or several match."""
    query = _norm(name)
    exact = [p for p in index if _norm(p.get("fullName", "")) == query]
    if len(exact) == 1:
        return int(exact[0]["id"])

    matches = exact or [p for p in index if query in _norm(p.get("fullName", ""))]
    if len(matches) == 1:
        return int(matches[0]["id"])
    if not matches:
        raise EspnError(f"No active player matches {name!r}.")

    top = sorted(matches, key=_owned, reverse=True)[:MAX_CANDIDATES]
    listed = "; ".join(_describe(p) for p in top)
    more = f" (+{len(matches) - len(top)} more)" if len(matches) > len(top) else ""
    raise EspnError(
        f"{name!r} matches {len(matches)} players{more}: {listed}. "
        "Retry with player_id or a fuller name."
    )
```

- [ ] **Step 5: Verify** — `uv run pytest -q` → `75 passed`

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_mcp/players.py tests/test_players.py tests/conftest.py tests/fixtures/players_index.json
git commit -m "feat: resolve player names against ESPN's player index"
```

---

### Task 3: `EspnClient.get_players_index`

**Files:**
- Modify: `src/fantasy_mcp/espn.py`
- Modify: `tests/test_espn.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add a URL constant to `tests/conftest.py`** (after `LEAGUE_URL`):

```python
PLAYERS_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/players"
```

- [ ] **Step 2: Append failing tests to `tests/test_espn.py`** (add `PLAYERS_URL` to the `from tests.conftest import ...` line):

```python
@respx.mock
def test_get_players_index_request_shape(settings):
    route = respx.get(PLAYERS_URL).mock(
        return_value=httpx.Response(200, json=[{"id": 1, "fullName": "A"}])
    )
    data = EspnClient(settings).get_players_index()
    assert data == [{"id": 1, "fullName": "A"}]
    req = route.calls.last.request
    assert req.url.params["scoringPeriodId"] == "0"
    assert req.url.params["view"] == "players_wl"
    assert json.loads(req.headers["x-fantasy-filter"]) == {"filterActive": {"value": True}}
    assert "espn_s2=s2-cookie" in req.headers["cookie"]


@respx.mock
def test_get_players_index_rejects_non_list(settings):
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json={"oops": 1}))
    with pytest.raises(EspnError, match="players index"):
        EspnClient(settings).get_players_index()


@respx.mock
def test_get_players_index_auth_error(settings):
    respx.get(PLAYERS_URL).mock(return_value=httpx.Response(401, text="nope"))
    with pytest.raises(EspnAuthError, match="cookies"):
        EspnClient(settings).get_players_index()
```

- [ ] **Step 3: Run to verify failure** — `uv run pytest tests/test_espn.py -v -k players_index` → 3 FAIL, `AttributeError: 'EspnClient' object has no attribute 'get_players_index'`

- [ ] **Step 4: Implement in `src/fantasy_mcp/espn.py`**

Replace the `get` method body so the HTTP call goes through a shared helper, and add `get_players_index`. The class should read:

```python
    def get(self, *views: str, fantasy_filter: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET the league endpoint with one or more ``view`` params."""
        headers = {"Accept": "application/json"}
        if fantasy_filter is not None:
            headers["X-Fantasy-Filter"] = json.dumps(fantasy_filter)
        return self._request(self.league_url, [("view", v) for v in views], headers)

    def get_players_index(self) -> list[dict[str, Any]]:
        """Active players for the season (league-independent); ~2.6k entries."""
        url = f"{BASE}/seasons/{self.settings.season}/players"
        headers = {
            "Accept": "application/json",
            "X-Fantasy-Filter": json.dumps({"filterActive": {"value": True}}),
        }
        data = self._request(url, [("scoringPeriodId", "0"), ("view", "players_wl")], headers)
        if not isinstance(data, list):
            raise EspnError("Unexpected players index response from ESPN (not a list).")
        return data

    def _request(self, url: str, params: list[tuple[str, str]], headers: dict[str, str]) -> Any:
        try:
            response = httpx.get(
                url, params=params, cookies=self._cookies, headers=headers, timeout=TIMEOUT_SECONDS
            )
        except httpx.RequestError as e:
            raise EspnError(f"Could not reach ESPN: {type(e).__name__}") from e
        return self._parse(response)
```

Change `_parse`'s return annotation from `-> dict[str, Any]` to `-> Any` (body may be a list). `find_my_team_id` and everything else unchanged.

- [ ] **Step 5: Verify** — `uv run pytest -q` → `78 passed`

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_mcp/espn.py tests/test_espn.py tests/conftest.py
git commit -m "feat: fetch ESPN's league-independent player index"
```

---

### Task 4: `filters.player_card_filter`

**Files:**
- Modify: `src/fantasy_mcp/filters.py`
- Modify: `tests/test_filters.py`

- [ ] **Step 1: Append failing test to `tests/test_filters.py`** (add `player_card_filter` to the import list):

```python
def test_player_card_filter_requests_totals_and_all_weekly_projections():
    out = player_card_filter(4242335, season=2026)
    players = out["players"]
    assert players["filterIds"] == {"value": [4242335]}
    top = players["filterStatsForTopScoringPeriodIds"]
    assert top["value"] == 17
    assert top["additionalValue"][:3] == ["002026", "102026", "002025"]
    assert top["additionalValue"][3:] == [f"112026{w}" for w in range(1, 19)]
    assert len(top["additionalValue"]) == 21
    assert set(players) == {"filterIds", "filterStatsForTopScoringPeriodIds"}
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_filters.py -v -k player_card` → `ImportError: cannot import name 'player_card_filter'`

- [ ] **Step 3: Append to `src/fantasy_mcp/filters.py`**

```python
WEEKS_IN_SEASON = 18


def player_card_filter(player_id: int, *, season: int) -> dict[str, Any]:
    """Filter for one player's card: season totals, last season, and weekly projections."""
    stat_ids = [f"00{season}", f"10{season}", f"00{season - 1}"]
    stat_ids += [f"11{season}{week}" for week in range(1, WEEKS_IN_SEASON + 1)]
    return {
        "players": {
            "filterIds": {"value": [player_id]},
            "filterStatsForTopScoringPeriodIds": {"value": 17, "additionalValue": stat_ids},
        }
    }
```

- [ ] **Step 4: Verify** — `uv run pytest -q` → `79 passed`

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/filters.py tests/test_filters.py
git commit -m "feat: build the player card X-Fantasy-Filter"
```

---

### Task 5: `player_id` on existing rows

**Files:**
- Modify: `src/fantasy_mcp/shapes.py`
- Modify: `tests/fixtures/mteam_mroster.json`, `tests/fixtures/matchup.json`, `tests/fixtures/free_agents.json`
- Modify: `tests/test_shapes.py`

- [ ] **Step 1: Add ids to fixtures**

`tests/fixtures/mteam_mroster.json` — team 3's three roster entries, in file order, each get a `"playerId"` key beside `"lineupSlotId"`: Bench Guy `101`, Josh Allen `102`, Flex Player `103`.

`tests/fixtures/matchup.json` — the eight `rosterForCurrentScoringPeriod.entries`, in file order, get `"playerId"`: Home Bench Guy `201`, Home Starter One `202`, Home IR Guy `203`, Home Starter NoStats `204`, Away Bench Guy `205`, Away Starter One `206`, Away IR Guy `207`, Away Starter NoStats `208`.

`tests/fixtures/free_agents.json` — the two `players[]` entries get a top-level `"id"` beside `"status"`: Waiver Back `301`, Sparse Receiver `302`.

Use a small script or careful edits; verify with `uv run python -c "import json; m=json.load(open('tests/fixtures/mteam_mroster.json')); print([e['playerId'] for e in m['teams'][0]['roster']['entries']])"` → `[101, 102, 103]`.

- [ ] **Step 2: Update tests in `tests/test_shapes.py`** so the exact-dict assertions include the id:

In `test_shape_team_orders_starters_first_and_maps_ids`, the `allen == {...}` dict gains `"player_id": 102,` as its first key.
In `test_shape_matchup_full_shape`, the `me["roster"][0] == {...}` dict gains `"player_id": 202,`.
In `test_shape_free_agent_full_entry`, the expected dict gains `"player_id": 301,`.
Add:
```python
def test_shape_player_id_falls_back_to_pool_entry_id():
    entry = {"lineupSlotId": 0, "playerPoolEntry": {"id": 555, "player": {"fullName": "X"}}}
    assert shapes._shape_player(entry)["player_id"] == 555
```

- [ ] **Step 3: Run to verify failure** — `uv run pytest tests/test_shapes.py -q` → 4 failures (three exact-dict mismatches + the new test).

- [ ] **Step 4: Implement in `src/fantasy_mcp/shapes.py`**

`_shape_player`:
```python
def _shape_player(entry: dict[str, Any]) -> dict[str, Any]:
    pool_entry = entry.get("playerPoolEntry") or {}
    player = pool_entry.get("player") or {}
    return {
        "player_id": entry.get("playerId", pool_entry.get("id")),
        "name": player.get("fullName"),
        "position": ids.name(ids.POSITIONS, player.get("defaultPositionId", -1)),
        "slot": ids.name(ids.LINEUP_SLOTS, entry.get("lineupSlotId", -1)),
        "pro_team": ids.name(ids.PRO_TEAMS, player.get("proTeamId", -1)),
        "injury_status": player.get("injuryStatus"),
    }
```
`shape_free_agent`: add `"player_id": entry.get("id"),` as the first key of the returned dict.

- [ ] **Step 5: Verify** — `uv run pytest -q` → `80 passed`

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_mcp/shapes.py tests/test_shapes.py tests/fixtures/mteam_mroster.json tests/fixtures/matchup.json tests/fixtures/free_agents.json
git commit -m "feat: expose player_id on roster and free-agent rows"
```

---

### Task 6: `shape_player_card`

**Files:**
- Add (untracked, on disk): `tests/fixtures/player_card.json`
- Modify: `tests/conftest.py`
- Modify: `src/fantasy_mcp/shapes.py`
- Modify: `tests/test_shapes.py`

Fixture facts (`player_card.json`): `seasonId 2026`, `scoringPeriodId 1`, one team (id 12 "My Matchup Team"), one player entry: id 4242335 "Card Back", RB, proTeamId 11 (IND), ACTIVE, `injured false`, `onTeamId 12`, `status ONTEAM`, `ratings["0"].positionalRanking 4`, eligibleSlots `[2, 3, 23, 7, 20, 21]`, outlook "Placeholder outlook: workhorse back with elite volume.", ownership 99.91 / 99.61 / 0.0 / ADP 6.36. Stats (file order): 2024 season decoy 777.7; 2026 wk1 actual 25.1 with raw `{"23":19,"24":98,"25":2,"41":3,"42":23,"53":3,"58":4,"68":1,"72":1,"156":1,"210":1}`; 2026 wk1 projection 17.75; 2026 season actual 25.1; 2026 season projection 315.58; 2025 season actual 362.3; 2025 wk18 actual 5.9 (`23:14, 24:26, 41:2, 42:13, 53:2, 58:2, 156:1, 210:1`); 2025 wk17 actual 17.4 (`23:21, 24:70, 25:1, 41:3, 42:14, 53:3, 58:6, 156:1, 210:1`).

- [ ] **Step 1: Verify fixture; add conftest fixture**

Run: `uv run python -c "import json; d=json.load(open('tests/fixtures/player_card.json')); print(d['scoringPeriodId'], d['players'][0]['player']['fullName'], len(d['players'][0]['player']['stats']))"` → `1 Card Back 9`. Missing → BLOCKED.

Append to `tests/conftest.py`:
```python


@pytest.fixture
def player_card_json() -> dict:
    return json.loads((FIXTURES / "player_card.json").read_text())
```

- [ ] **Step 2: Append failing tests to `tests/test_shapes.py`**

```python
def test_shape_player_card_full(player_card_json):
    entry = player_card_json["players"][0]
    out = shapes.shape_player_card(entry, player_card_json)

    assert {k: out[k] for k in ("player_id", "name", "position", "pro_team", "injury_status", "injured")} == {
        "player_id": 4242335,
        "name": "Card Back",
        "position": "RB",
        "pro_team": "IND",
        "injury_status": "ACTIVE",
        "injured": False,
    }
    assert out["eligible_slots"] == ["RB", "RB/WR", "FLEX", "OP"]
    assert out["league_status"] == "ONTEAM"
    assert out["owned_by"] == {"team_id": 12, "name": "My Matchup Team"}
    assert out["ownership"] == {
        "percent_owned": 99.9,
        "percent_started": 99.6,
        "percent_change": 0.0,
        "adp": 6.4,
    }
    assert out["season"] == {"year": 2026, "projected": 315.58, "points": 25.1, "positional_rank": 4}
    assert out["last_season"] == {"year": 2025, "points": 362.3}
    assert out["outlook"] == "Placeholder outlook: workhorse back with elite volume."

    log = out["game_log"]
    assert [(g["season"], g["week"]) for g in log] == [(2026, 1), (2025, 18), (2025, 17)]
    assert log[0] == {
        "season": 2026,
        "week": 1,
        "points": 25.1,
        "projected": 17.75,
        "stats": {
            "rush_att": 19,
            "rush_yds": 98,
            "rush_td": 2,
            "rec_yds": 23,
            "receptions": 3,
            "targets": 4,
            "fumbles": 1,
            "fumbles_lost": 1,
            "team_loss": 1,
            "games_played": 1,
        },
    }
    assert log[1]["projected"] is None
    assert log[1]["stats"]["rush_yds"] == 26
    assert "41" not in str(log)  # unmapped raw id never leaks


def test_shape_player_card_unrostered_and_sparse(player_card_json):
    entry = player_card_json["players"][0]
    entry["onTeamId"] = 0
    entry["status"] = "WAIVERS"
    entry["ratings"]["0"]["positionalRanking"] = 0
    entry["player"]["seasonOutlook"] = ""
    del entry["player"]["ownership"]
    out = shapes.shape_player_card(entry, player_card_json)
    assert out["owned_by"] is None
    assert out["league_status"] == "WAIVERS"
    assert out["season"]["positional_rank"] is None
    assert out["outlook"] is None
    assert out["ownership"] == {
        "percent_owned": None,
        "percent_started": None,
        "percent_change": None,
        "adp": None,
    }


def test_shape_player_card_no_last_season():
    league = {"seasonId": 2026, "scoringPeriodId": 1, "teams": []}
    entry = {"id": 9, "onTeamId": 0, "status": "FREEAGENT", "player": {"fullName": "Rookie", "stats": []}}
    out = shapes.shape_player_card(entry, league)
    assert out["last_season"] is None
    assert out["season"] == {"year": 2026, "projected": None, "points": None, "positional_rank": None}
    assert out["game_log"] == []
    assert out["eligible_slots"] == []
```

- [ ] **Step 3: Run to verify failure** — `uv run pytest tests/test_shapes.py -v -k player_card` → 3 FAIL, `AttributeError: module 'fantasy_mcp.shapes' has no attribute 'shape_player_card'`

- [ ] **Step 4: Implement** — add `from fantasy_mcp.stats import shape_stat_line` to the imports of `src/fantasy_mcp/shapes.py`, then append:

```python
_NON_STARTING_SLOTS = {20, 21}  # BENCH, IR


def _game_log(player: dict[str, Any], season: int) -> list[dict[str, Any]]:
    seasons = {season, season - 1}
    projections = {
        (s.get("seasonId"), s.get("scoringPeriodId")): _round(s.get("appliedTotal"))
        for s in player.get("stats") or []
        if s.get("statSourceId") == PROJECTION_SOURCE_ID and s.get("scoringPeriodId", 0) > 0
    }
    rows = []
    for s in player.get("stats") or []:
        year, week = s.get("seasonId"), s.get("scoringPeriodId") or 0
        if s.get("statSourceId") != ACTUAL_SOURCE_ID or week <= 0 or year not in seasons:
            continue
        rows.append(
            {
                "season": year,
                "week": week,
                "points": _round(s.get("appliedTotal")),
                "projected": projections.get((year, week)),
                "stats": shape_stat_line(s.get("stats")),
            }
        )
    rows.sort(key=lambda r: (r["season"], r["week"]), reverse=True)
    return rows


def shape_player_card(entry: dict[str, Any], league: dict[str, Any]) -> dict[str, Any]:
    """Shape one kona_playercard players[] entry into a full player profile."""
    season = league.get("seasonId", -1)
    player = entry.get("player") or {}
    ownership = player.get("ownership") or {}
    rank = ((entry.get("ratings") or {}).get("0") or {}).get("positionalRanking") or None
    team = _find_team(league, entry.get("onTeamId")) if entry.get("onTeamId") else None
    last_points = _stat(player, period=SEASON_PERIOD, source=ACTUAL_SOURCE_ID, season=season - 1)
    return {
        "player_id": entry.get("id", player.get("id")),
        "name": player.get("fullName"),
        "position": ids.name(ids.POSITIONS, player.get("defaultPositionId", -1)),
        "pro_team": ids.name(ids.PRO_TEAMS, player.get("proTeamId", -1)),
        "injury_status": player.get("injuryStatus"),
        "injured": player.get("injured"),
        "eligible_slots": [
            ids.name(ids.LINEUP_SLOTS, slot)
            for slot in player.get("eligibleSlots") or []
            if slot not in _NON_STARTING_SLOTS
        ],
        "league_status": entry.get("status"),
        "owned_by": {"team_id": team.get("id"), "name": team.get("name")} if team else None,
        "ownership": {
            "percent_owned": _round(ownership.get("percentOwned"), ndigits=1),
            "percent_started": _round(ownership.get("percentStarted"), ndigits=1),
            "percent_change": _round(ownership.get("percentChange"), ndigits=1),
            "adp": _round(ownership.get("averageDraftPosition"), ndigits=1),
        },
        "season": {
            "year": season,
            "projected": _stat(player, period=SEASON_PERIOD, source=PROJECTION_SOURCE_ID, season=season),
            "points": _stat(player, period=SEASON_PERIOD, source=ACTUAL_SOURCE_ID, season=season),
            "positional_rank": rank,
        },
        "last_season": {"year": season - 1, "points": last_points} if last_points is not None else None,
        "outlook": player.get("seasonOutlook") or None,
        "game_log": _game_log(player, season),
    }
```

- [ ] **Step 5: Verify** — `uv run pytest -q` → `83 passed`

Troubleshooting: if `eligible_slots` order differs, it must follow the fixture's list order (`[2, 3, 23, 7]` → RB, RB/WR, FLEX, OP). If `percent_change` is `0.0` vs `0`, `_round` returns float `0.0` — the test expects `0.0`.

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_mcp/shapes.py tests/test_shapes.py tests/conftest.py tests/fixtures/player_card.json
git commit -m "feat: shape a full player card with game log"
```

---

### Task 7: `get_player` tool, index cache, instructions, README

**Files:**
- Modify: `src/fantasy_mcp/server.py`
- Modify: `tests/test_server.py`
- Modify: `README.md`

- [ ] **Step 1: Append failing tests to `tests/test_server.py`** (add `PLAYERS_URL` to the `from tests.conftest import ...` line):

```python
@pytest.fixture
def cached_index(players_index):
    server.set_players_index_for_tests(players_index)
    yield players_index
    server.set_players_index_for_tests(None)


@respx.mock
async def test_get_player_by_name(client, cached_index, player_card_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=player_card_json))
    index_route = respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json=[]))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_player", {"name": "jonathan taylor"})
    assert result.data["player_id"] == 4242335
    assert result.data["name"] == "Card Back"
    assert result.data["owned_by"]["team_id"] == 12
    assert not index_route.called  # cache injected, no index fetch
    req = route.calls.last.request
    assert req.url.params.get_list("view") == ["kona_playercard", "mTeam", "mStatus"]
    sent = json.loads(req.headers["x-fantasy-filter"])["players"]
    assert sent["filterIds"] == {"value": [4242335]}
    assert len(sent["filterStatsForTopScoringPeriodIds"]["additionalValue"]) == 21


@respx.mock
async def test_get_player_by_id_skips_index(client, player_card_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=player_card_json))
    index_route = respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json=[]))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_player", {"player_id": 4242335})
    assert result.data["player_id"] == 4242335
    assert not index_route.called


@respx.mock
async def test_get_player_fetches_and_caches_index(client, players_index, player_card_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=player_card_json))
    index_route = respx.get(PLAYERS_URL).mock(return_value=httpx.Response(200, json=players_index))
    server.set_players_index_for_tests(None)
    try:
        async with Client(server.mcp) as c:
            await c.call_tool("get_player", {"name": "Jonathan Taylor"})
            await c.call_tool("get_player", {"name": "Jonathan Taylor"})
    finally:
        server.set_players_index_for_tests(None)
    assert index_route.call_count == 1


@respx.mock
@pytest.mark.parametrize("args", [{}, {"name": "x", "player_id": 1}])
async def test_get_player_requires_exactly_one_arg(client, args):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="exactly one of name or player_id"):
            await c.call_tool("get_player", args)
    assert not route.called


@respx.mock
async def test_get_player_ambiguous_name_is_tool_error(client, cached_index):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="id 4572680"):
            await c.call_tool("get_player", {"name": "tucker"})
    assert not route.called


@respx.mock
async def test_get_player_unknown_id_is_tool_error(client):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={"players": [], "teams": []}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="no player with id 42"):
            await c.call_tool("get_player", {"player_id": 42})
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_server.py -v -k get_player` → failures (`set_players_index_for_tests` missing / unknown tool).

- [ ] **Step 3: Implement in `src/fantasy_mcp/server.py`**

Imports — extend:
```python
from fantasy_mcp.filters import FilterError, free_agent_filter, normalize_position, player_card_filter
from fantasy_mcp.players import resolve_player
from fantasy_mcp.shapes import (
    find_matchup,
    shape_free_agent,
    shape_matchup,
    shape_player_card,
    shape_team,
    shape_whoami,
    team_by_id,
)
```

After `set_client_for_tests`, add the index cache:
```python
_players_index: list[dict[str, Any]] | None = None


def _get_players_index(client: EspnClient) -> list[dict[str, Any]]:
    """ESPN's active-player index, fetched once per process (used for name lookup)."""
    global _players_index
    if _players_index is None:
        _players_index = client.get_players_index()
    return _players_index


def set_players_index_for_tests(index: list[dict[str, Any]] | None) -> None:
    global _players_index
    _players_index = index
```

Add the tool after `get_free_agents` (before `def main()`):
```python
@mcp.tool
def get_player(name: str | None = None, player_id: int | None = None) -> dict[str, Any]:
    """Full profile for one player: status, league ownership, season numbers, outlook, game log.

    Use this for "tell me about X", "how has X been doing", "who has X in my
    league", or "is X worth a claim". Pass exactly one of: name (full name is
    best; a partial name works if it matches one active player) or player_id
    (from any other tool's rows -- prefer this when you have it).

    Returns: player_id, name, position, pro_team, injury_status, injured,
    eligible_slots; league_status (ONTEAM / FREEAGENT / WAIVERS) and owned_by
    (the league team rostering them, or null); ownership across all ESPN leagues
    (percent_owned, percent_started, percent_change = trend, adp); season
    {year, projected, points, positional_rank}; last_season {year, points};
    outlook (ESPN's written preseason summary); game_log newest first, each
    week with points, projected (null until ESPN publishes it), and stats --
    raw counts such as rush_yds, targets, pass_td, fg_made_40_49, dst_sacks
    (zero-valued stats omitted). Covers this season and last. No news
    articles or opponent-matchup ratings.
    """
    if (name is None) == (player_id is None):
        raise ToolError("Pass exactly one of name or player_id.")
    try:
        client = _get_client()
        if player_id is None:
            player_id = resolve_player(name, _get_players_index(client))
        fantasy_filter = player_card_filter(player_id, season=client.settings.season)
        league = client.get("kona_playercard", "mTeam", "mStatus", fantasy_filter=fantasy_filter)
        entries = league.get("players") or []
        if not entries:
            raise EspnError(f"ESPN returned no player with id {player_id}.")
        return shape_player_card(entries[0], league)
    except (FilterError, EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e
```

- [ ] **Step 4: Update `INSTRUCTIONS`.** Replace:
```
roster from get_my_team before recommending a move. Only whoami, get_my_team,
get_matchup, and get_free_agents exist. There is no standings, transaction,
or past-week data yet -- say so instead of inventing it.
```
with:
```
roster from get_my_team before recommending a move. Use get_player for
questions about a specific player (history, outlook, who owns them); pass
player_id from another tool's output when you have it. Only whoami,
get_my_team, get_matchup, get_free_agents, and get_player exist. There is no
standings, transaction, or past-week matchup data yet -- say so instead of
inventing it.
```

- [ ] **Step 5: Verify** — `uv run pytest -q` → `90 passed`. Registration:
```
uv run python -c "
import asyncio
from fastmcp import Client
from fantasy_mcp import server
async def m():
    async with Client(server.mcp) as c:
        print(sorted(t.name for t in await c.list_tools()))
asyncio.run(m())"
```
→ `['get_free_agents', 'get_matchup', 'get_my_team', 'get_player', 'whoami']`

- [ ] **Step 6: `README.md`** — in `## Tools`, add after the `get_free_agents` bullet:
```markdown
- `get_player` — one player's full profile by name or id: league ownership,
  season totals/projection, ESPN outlook, and a per-week game log with stat
  lines for this season and last.
```

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_mcp/server.py tests/test_server.py README.md
git commit -m "feat: add get_player tool with name resolution"
```

---

### Task 8: Live smoke test + stat-id verification

Run by the controller (needs `.env`). Not delegated.

- [ ] **Step 1: Call the tool for a QB, RB, K, D/ST**

```bash
uv run python - <<'EOF'
import asyncio
from fastmcp import Client
from fantasy_mcp import server
async def main():
    async with Client(server.mcp) as c:
        for args in ({"name": "Jayden Daniels"}, {"player_id": 4242335}, {"name": "Tyler Loop"}, {"name": "Ravens D/ST"}):
            p = (await c.call_tool("get_player", args)).data
            print(f'\n{p["name"]} {p["position"]} {p["pro_team"]} {p["league_status"]} owned_by={p["owned_by"]} rank={p["season"]["positional_rank"]}')
            print("  season:", p["season"], "| last:", p["last_season"], "| own:", p["ownership"])
            print("  slots:", p["eligible_slots"], "| outlook:", (p["outlook"] or "")[:80])
            for g in p["game_log"][:3]:
                print(f'  {g["season"]} wk{g["week"]:<2} pts={g["points"]} proj={g["projected"]} {g["stats"]}')
        try:
            await c.call_tool("get_player", {"name": "tucker"})
        except Exception as e:
            print("\nambiguous ->", str(e)[:200])
asyncio.run(main())
EOF
```

- [ ] **Step 2: Cross-check week-1 stat lines against ESPN's box score** (fetch the game summary pages or the ESPN app): Daniels 17/32, 163 yds, 1 TD, 5 rush / 31; Taylor 19 rush / 98 / 2 TD, 3 rec / 23 on 4 targets, 1 fumble lost; Loop 2/2 FG (one 50+, one 40–49), 5/5 XP; Ravens D/ST 2 sacks, 1 INT, 1 fumble rec, 23 points allowed, and `dst_yards_allowed` vs the box score's total yards. Any mismatch → fix `STAT_NAMES` (commit `fix: correct ESPN stat id <n>`).

- [ ] **Step 3: Verify from Claude Code** — restart `claude`, `/mcp`, ask "tell me about Tre Tucker" and "who has Christian McCaffrey in my league?".
