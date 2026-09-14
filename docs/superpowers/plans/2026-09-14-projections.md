# `get_projections` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `get_projections(week)` — weekly projections for the user's roster with opponent/bye/kickoff and a suggested optimal lineup with explicit changes.

**Architecture:** `espn.get` gains a `scoring_period` query param and `get_pro_schedules()`; `filters.player_ids_filter`; two new pure modules `schedules.py` (opponent/kickoff lookup) and `lineup.py` (greedy optimal lineup); `shapes.shape_projections` composes them; `server.get_projections` orchestrates two ESPN calls plus a cached schedules call.

**Spec:** `docs/superpowers/specs/2026-09-14-projections-design.md` (authoritative). Fixtures already committed: `tests/fixtures/roster_settings.json`, `projections.json`, `pro_schedules.json`.

Fixture facts: roster entries (playerId, slot): QB One 4426348/0, RB One 4242335/2, WR One 4361370/4, WR Two 4569618/4, TE One 4361050/6, Def One -16033/16, Kicker One 4697745/17, WR Bench 3916433/20; FLEX(23) empty; `lineupSlotCounts` {0:1,2:2,4:2,6:1,16:1,17:1,20:7,21:1,23:1}. Week-2 projections: QB One 19.4, RB One 17.68, WR One 15.25, WR Two 14.73, TE One 9.96, Def One 6.82, Kicker One 8.92, WR Bench 10.02. eligibleSlots: QB [0,7,20,21]; RB [2,3,23,7,20,21]; WRs [3,4,5,23,7,20,21]; TE [5,6,23,7,20,21]; D/ST [16,20,21]; K [17,20,21]. Pro teams: IND(11) week 2 away at KC(12) date 1789950000000 → `2026-09-21T00:20:00Z`; BAL(33) home vs NO(18); byes IND 13, BAL 13, WSH 7. Current starters total = 92.76; with WR Bench at FLEX = 102.78.

---

### Task 1: client + filter + `schedules.py` + `lineup.py`

**Files:** `src/fantasy_mcp/espn.py`, `src/fantasy_mcp/filters.py`, `src/fantasy_mcp/schedules.py` (new), `src/fantasy_mcp/lineup.py` (new), `tests/conftest.py`, `tests/test_espn.py`, `tests/test_filters.py`, `tests/test_schedules.py` (new), `tests/test_lineup.py` (new)

- [ ] **Step 1: conftest** — append three fixtures (same style as the others): `roster_settings_json`, `projections_json`, `pro_schedules_json` loading the three files. Add `SEASON_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026"` after `PLAYERS_URL`.

- [ ] **Step 2: failing tests.**

`tests/test_espn.py` (add `SEASON_URL` to the conftest import):
```python
@respx.mock
def test_get_sends_scoring_period_param(settings, league_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    EspnClient(settings).get("kona_player_info", scoring_period=2)
    assert route.calls.last.request.url.params["scoringPeriodId"] == "2"


@respx.mock
def test_get_omits_scoring_period_by_default(settings, league_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    EspnClient(settings).get("mTeam")
    assert "scoringPeriodId" not in route.calls.last.request.url.params


@respx.mock
def test_get_pro_schedules(settings, pro_schedules_json):
    route = respx.get(SEASON_URL).mock(return_value=httpx.Response(200, json=pro_schedules_json))
    data = EspnClient(settings).get_pro_schedules()
    assert data["settings"]["proTeams"][0]["abbrev"]
    req = route.calls.last.request
    assert req.url.params["view"] == "proTeamSchedules_wl"
    assert "espn_s2=s2-cookie" in req.headers["cookie"]


@respx.mock
def test_get_pro_schedules_rejects_non_object(settings):
    respx.get(SEASON_URL).mock(return_value=httpx.Response(200, json=[1]))
    with pytest.raises(EspnError, match="schedules"):
        EspnClient(settings).get_pro_schedules()
```
`tests/test_filters.py` (add `player_ids_filter` to the import):
```python
def test_player_ids_filter():
    out = player_ids_filter([3, 1, 2])
    assert out == {"players": {"filterIds": {"value": [3, 1, 2]}}}
    out["players"]["filterIds"]["value"].append(9)
    assert player_ids_filter([3, 1, 2])["players"]["filterIds"]["value"] == [3, 1, 2]
```
`tests/test_schedules.py`:
```python
from fantasy_mcp.schedules import game_context


def test_away_game(pro_schedules_json):
    assert game_context(pro_schedules_json, 11, 2) == {"opponent": "@KC", "kickoff": "2026-09-21T00:20:00Z"}


def test_home_game(pro_schedules_json):
    assert game_context(pro_schedules_json, 33, 2)["opponent"] == "vs NO"


def test_bye_week(pro_schedules_json):
    assert game_context(pro_schedules_json, 11, 13) == {"opponent": "BYE", "kickoff": None}


def test_no_game_that_week_is_bye(pro_schedules_json):
    for team in pro_schedules_json["settings"]["proTeams"]:
        if team["id"] == 11:
            team["proGamesByScoringPeriod"].pop("2")
    assert game_context(pro_schedules_json, 11, 2)["opponent"] == "BYE"


def test_unknown_team_or_empty_schedules(pro_schedules_json):
    assert game_context(pro_schedules_json, 999, 2) == {"opponent": None, "kickoff": None}
    assert game_context({}, 11, 2) == {"opponent": None, "kickoff": None}
    assert game_context(pro_schedules_json, None, 2) == {"opponent": None, "kickoff": None}
```
`tests/test_lineup.py`:
```python
from fantasy_mcp.lineup import optimal_lineup

SLOTS = {0: 1, 2: 2, 4: 2, 6: 1, 16: 1, 17: 1, 20: 7, 21: 1, 23: 1}


def _p(pid, proj, eligible, slot=20):
    return {"player_id": pid, "projected": proj, "eligible_slots": eligible, "slot_id": slot}


def test_fills_dedicated_then_flex_by_projection():
    players = [
        _p(1, 19.4, [0, 7, 20, 21], slot=0),
        _p(2, 17.7, [2, 3, 23, 7, 20, 21], slot=2),
        _p(3, 12.0, [2, 3, 23, 7, 20, 21]),          # bench RB
        _p(4, 15.3, [3, 4, 5, 23, 7, 20, 21], slot=4),
        _p(5, 14.7, [3, 4, 5, 23, 7, 20, 21], slot=4),
        _p(6, 10.0, [3, 4, 5, 23, 7, 20, 21]),        # bench WR
        _p(7, 9.9, [5, 6, 23, 7, 20, 21], slot=6),
        _p(8, 6.8, [16, 20, 21], slot=16),
        _p(9, 8.9, [17, 20, 21], slot=17),
    ]
    out = optimal_lineup(players, SLOTS)
    assert [p["player_id"] for p in out[0]] == [1]
    assert [p["player_id"] for p in out[2]] == [2, 3]        # second RB slot takes the bench RB
    assert [p["player_id"] for p in out[4]] == [4, 5]
    assert [p["player_id"] for p in out[23]] == [6]          # flex gets the best remaining
    assert set(out) == {0, 2, 4, 6, 16, 17, 23}               # no bench/IR keys


def test_ir_players_are_never_moved():
    players = [_p(1, 30.0, [2, 23, 20, 21], slot=21), _p(2, 5.0, [2, 23, 20, 21], slot=2)]
    out = optimal_lineup(players, {2: 1, 23: 1, 20: 1, 21: 1})
    assert [p["player_id"] for p in out[2]] == [2]
    assert out[23] == []


def test_tie_keeps_current_starter_and_none_projection_is_zero():
    players = [_p(1, 10.0, [4, 20], slot=20), _p(2, 10.0, [4, 20], slot=4), _p(3, None, [4, 20])]
    out = optimal_lineup(players, {4: 1, 20: 2})
    assert [p["player_id"] for p in out[4]] == [2]


def test_slot_count_exceeds_players():
    out = optimal_lineup([_p(1, 5.0, [4, 20])], {4: 2, 20: 1})
    assert [p["player_id"] for p in out[4]] == [1]
```

- [ ] **Step 3:** run the four test files → import/attribute failures.

- [ ] **Step 4: implement.**

`src/fantasy_mcp/espn.py` — change `get`:
```python
    def get(
        self,
        *views: str,
        fantasy_filter: dict[str, Any] | None = None,
        scoring_period: int | None = None,
    ) -> dict[str, Any]:
        """GET the league endpoint with one or more ``view`` params.

        ``scoring_period`` selects which NFL week's per-player stats/projections
        ESPN includes (defaults to the current week).
        """
        headers = {"Accept": "application/json"}
        if fantasy_filter is not None:
            headers["X-Fantasy-Filter"] = json.dumps(fantasy_filter)
        params: list[tuple[str, str]] = [("view", v) for v in views]
        if scoring_period is not None:
            params.append(("scoringPeriodId", str(scoring_period)))
        s = self.settings
        data = self._request(
            self.league_url,
            params,
            headers,
            not_found=f"league {s.league_id}, season {s.season}. Check ESPN_LEAGUE_ID and ESPN_SEASON",
        )
        if not isinstance(data, dict):
            raise EspnError("Unexpected league response from ESPN (not an object).")
        return data
```
Add after `get_players_index`:
```python
    def get_pro_schedules(self) -> dict[str, Any]:
        """NFL teams with bye weeks and per-week games (league-independent)."""
        url = f"{BASE}/seasons/{self.settings.season}"
        data = self._request(
            url,
            [("view", "proTeamSchedules_wl")],
            {"Accept": "application/json"},
            not_found=f"the season {self.settings.season} pro schedules. Check ESPN_SEASON",
        )
        if not isinstance(data, dict):
            raise EspnError("Unexpected pro schedules response from ESPN (not an object).")
        return data
```
`src/fantasy_mcp/filters.py` — append:
```python
def player_ids_filter(player_ids: list[int]) -> dict[str, Any]:
    """Filter restricting a player view to specific ESPN player ids."""
    return {"players": {"filterIds": {"value": list(player_ids)}}}
```
`src/fantasy_mcp/schedules.py`:
```python
"""Opponent / bye / kickoff lookup from ESPN's pro team schedules."""

from __future__ import annotations

import datetime as dt
from typing import Any


def _teams(schedules: dict[str, Any]) -> dict[int, dict[str, Any]]:
    teams = (schedules.get("settings") or {}).get("proTeams") or []
    return {t["id"]: t for t in teams if isinstance(t, dict) and "id" in t}


def _iso(epoch_ms: Any) -> str | None:
    if not epoch_ms:
        return None
    return (
        dt.datetime.fromtimestamp(int(epoch_ms) / 1000, dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def game_context(schedules: dict[str, Any], pro_team_id: int | None, week: int) -> dict[str, Any]:
    """``{"opponent": "@KC" | "vs BUF" | "BYE" | None, "kickoff": ISO-8601 UTC | None}``."""
    teams = _teams(schedules)
    team = teams.get(pro_team_id) if pro_team_id is not None else None
    if team is None:
        return {"opponent": None, "kickoff": None}
    games = (team.get("proGamesByScoringPeriod") or {}).get(str(week)) or []
    if team.get("byeWeek") == week or not games:
        return {"opponent": "BYE", "kickoff": None}
    game = games[0]
    home = game.get("homeProTeamId") == pro_team_id
    other_id = game.get("awayProTeamId") if home else game.get("homeProTeamId")
    other = (teams.get(other_id) or {}).get("abbrev") or "?"
    return {"opponent": f"{'vs' if home else '@'} {other.upper()}", "kickoff": _iso(game.get("date"))}
```
`src/fantasy_mcp/lineup.py`:
```python
"""Greedy optimal-lineup assignment for a fantasy roster."""

from __future__ import annotations

from typing import Any

DEDICATED_SLOTS = (0, 2, 4, 6, 16, 17)  # QB, RB, WR, TE, D/ST, K
NON_STARTING_SLOTS = {20, 21}  # BENCH, IR
IR_SLOT = 21


def _projection(player: dict[str, Any]) -> float:
    value = player.get("projected")
    return float(value) if value is not None else 0.0


def _fill(slot_id: int, count: int, pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [p for p in pool if slot_id in (p.get("eligible_slots") or [])]
    eligible.sort(key=lambda p: (-_projection(p), p.get("slot_id") != slot_id, p.get("player_id") or 0))
    chosen = eligible[:count]
    for p in chosen:
        pool.remove(p)
    return chosen


def optimal_lineup(players: list[dict[str, Any]], slot_counts: dict[int, int]) -> dict[int, list[dict[str, Any]]]:
    """Assign players to starting slots to maximize total projection.

    Dedicated slots are filled first (they never compete with each other), then
    flex-type slots take the best remaining eligible players. Players on IR are
    never moved. Returns ``{slot_id: [player rows]}`` for starting slots only.
    """
    pool = [p for p in players if p.get("slot_id") != IR_SLOT]
    starting = {int(s): int(n) for s, n in slot_counts.items() if int(s) not in NON_STARTING_SLOTS and n}
    result: dict[int, list[dict[str, Any]]] = {}
    for slot_id in DEDICATED_SLOTS:
        if slot_id in starting:
            result[slot_id] = _fill(slot_id, starting[slot_id], pool)
    for slot_id in sorted(s for s in starting if s not in DEDICATED_SLOTS):
        result[slot_id] = _fill(slot_id, starting[slot_id], pool)
    return result
```

- [ ] **Step 5:** `uv run pytest -q` → `150 passed` (133 + 4 espn + 1 filters + 5 schedules + 4 lineup = 147 … recount after running; report the actual number).
- [ ] **Step 6:** Commit `feat: scoring-period requests, pro schedules, and lineup optimizer`.

---

### Task 2: `shape_projections` + tool

**Files:** `src/fantasy_mcp/shapes.py`, `src/fantasy_mcp/server.py`, `tests/test_shapes.py`, `tests/test_server.py`, `README.md`

- [ ] **Step 1: failing tests.** `tests/test_shapes.py`:
```python
def _proj_args(roster_settings_json, projections_json, pro_schedules_json):
    team = roster_settings_json["teams"][0]
    counts = {int(k): v for k, v in roster_settings_json["settings"]["rosterSettings"]["lineupSlotCounts"].items()}
    return 2, team["roster"]["entries"], projections_json["players"], pro_schedules_json, counts


def test_shape_projections_rows_and_lineup(roster_settings_json, projections_json, pro_schedules_json):
    out = shapes.shape_projections(*_proj_args(roster_settings_json, projections_json, pro_schedules_json))
    assert out["week"] == 2
    names = [p["name"] for p in out["players"]]
    assert names == ["QB One", "RB One", "WR One", "WR Two", "TE One", "Def One", "Kicker One", "WR Bench"]
    rb = out["players"][1]
    assert rb == {
        "player_id": 4242335, "name": "RB One", "position": "RB", "pro_team": "IND",
        "injury_status": "ACTIVE", "slot": "RB", "opponent": "@KC",
        "kickoff": "2026-09-21T00:20:00Z", "projected": 17.68,
    }
    assert out["players"][5]["opponent"] == "vs NO"
    assert out["current_total"] == 92.76
    assert out["suggested_total"] == 102.78
    assert [(r["slot"], r["name"]) for r in out["suggested_lineup"]] == [
        ("QB", "QB One"), ("RB", "RB One"), ("WR", "WR One"), ("WR", "WR Two"), ("TE", "TE One"),
        ("D/ST", "Def One"), ("K", "Kicker One"), ("FLEX", "WR Bench"),
    ]
    assert out["changes"] == {
        "start": [{"slot": "FLEX", "player_id": 3916433, "name": "WR Bench", "projected": 10.02}],
        "sit": [],
        "gain": 10.02,
    }


def test_shape_projections_bye_and_missing_projection(roster_settings_json, projections_json, pro_schedules_json):
    for team in pro_schedules_json["settings"]["proTeams"]:
        if team["id"] == 11:
            team["byeWeek"] = 2
    projections_json["players"] = [p for p in projections_json["players"] if p["id"] != 4361050]  # drop TE
    out = shapes.shape_projections(*_proj_args(roster_settings_json, projections_json, pro_schedules_json))
    rb = next(p for p in out["players"] if p["name"] == "RB One")
    assert rb["opponent"] == "BYE" and rb["kickoff"] is None
    te = next(p for p in out["players"] if p["name"] == "TE One")
    assert te["projected"] is None
    assert out["current_total"] == round(92.76 - 9.96, 2)


def test_shape_projections_empty_inputs():
    out = shapes.shape_projections(1, [], [], {}, {})
    assert out == {"week": 1, "players": [], "current_total": 0, "suggested_lineup": [],
                   "suggested_total": 0, "changes": {"start": [], "sit": [], "gain": 0}}
```
`tests/test_server.py`:
```python
@pytest.fixture
def cached_schedules(pro_schedules_json):
    server.set_pro_schedules_for_tests(pro_schedules_json)
    yield pro_schedules_json
    server.set_pro_schedules_for_tests(None)


@respx.mock
async def test_get_projections_tool(client, cached_schedules, roster_settings_json, projections_json):
    def respond(request):
        views = request.url.params.get_list("view")
        return httpx.Response(200, json=projections_json if "kona_player_info" in views else roster_settings_json)

    route = respx.get(LEAGUE_URL).mock(side_effect=respond)
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_projections", {"week": 2})
    assert result.data["week"] == 2
    assert result.data["changes"]["start"][0]["name"] == "WR Bench"
    calls = [r.request for r in route.calls]
    assert calls[0].url.params.get_list("view") == ["mRoster", "mSettings"]
    assert calls[1].url.params.get_list("view") == ["kona_player_info"]
    assert calls[1].url.params["scoringPeriodId"] == "2"
    sent = json.loads(calls[1].headers["x-fantasy-filter"])["players"]["filterIds"]["value"]
    assert 4242335 in sent and len(sent) == 8


@respx.mock
async def test_get_projections_defaults_to_current_week(client, cached_schedules, roster_settings_json, projections_json):
    def respond(request):
        views = request.url.params.get_list("view")
        return httpx.Response(200, json=projections_json if "kona_player_info" in views else roster_settings_json)

    route = respx.get(LEAGUE_URL).mock(side_effect=respond)
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_projections", {})
    assert result.data["week"] == 1
    assert route.calls[1].request.url.params["scoringPeriodId"] == "1"


@respx.mock
@pytest.mark.parametrize("week", [0, 19])
async def test_get_projections_rejects_bad_week(client, week):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="week must be between 1 and 18"):
            await c.call_tool("get_projections", {"week": week})
    assert not route.called


async def test_seven_tools_registered(client):
    async with Client(server.mcp) as c:
        names = sorted(t.name for t in await c.list_tools())
    assert names == ["get_free_agents", "get_league_settings", "get_matchup", "get_my_team",
                     "get_player", "get_projections", "whoami"]
```
Also delete `test_six_tools_registered` (superseded).

- [ ] **Step 2:** run → failures.

- [ ] **Step 3: implement `shapes.py`.** Add imports `from fantasy_mcp.lineup import NON_STARTING_SLOTS, optimal_lineup` and `from fantasy_mcp.schedules import game_context`. Append:
```python
def _projection_for(player: dict[str, Any], week: int, season: int) -> float | None:
    return _stat(player, period=week, source=PROJECTION_SOURCE_ID, season=season)


def _lineup_row(slot_id: int, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot": ids.name(ids.LINEUP_SLOTS, slot_id),
        "player_id": row["player_id"],
        "name": row["name"],
        "projected": row["projected"],
    }


def shape_projections(
    week: int,
    roster_entries: list[dict[str, Any]],
    projections_players: list[dict[str, Any]],
    schedules: dict[str, Any],
    slot_counts: dict[int, int],
) -> dict[str, Any]:
    """Weekly projections for a roster plus a suggested optimal lineup and the changes to reach it."""
    by_id = {p.get("id"): p.get("player") or {} for p in projections_players or []}
    season = next((s.get("seasonId") for p in by_id.values() for s in (p.get("stats") or [])), -1)

    rows: list[dict[str, Any]] = []
    for entry in roster_entries or []:
        base = _shape_player(entry)
        player = by_id.get(base["player_id"]) or (entry.get("playerPoolEntry") or {}).get("player") or {}
        pro_team_id = player.get("proTeamId")
        context = game_context(schedules, pro_team_id, week)
        rows.append(
            {
                **{k: base[k] for k in ("player_id", "name", "position", "pro_team", "injury_status", "slot")},
                "opponent": context["opponent"],
                "kickoff": context["kickoff"],
                "projected": _projection_for(player, week, season) if by_id.get(base["player_id"]) else None,
                "_slot_id": entry.get("lineupSlotId", 99),
                "_eligible": player.get("eligibleSlots") or [],
            }
        )

    starters = [r for r in rows if r["_slot_id"] not in NON_STARTING_SLOTS]
    others = [r for r in rows if r["_slot_id"] in NON_STARTING_SLOTS]
    starters.sort(key=lambda r: r["_slot_id"])
    others.sort(key=lambda r: -(r["projected"] or 0))
    ordered = starters + others

    lineup_input = [
        {"player_id": r["player_id"], "name": r["name"], "projected": r["projected"],
         "eligible_slots": r["_eligible"], "slot_id": r["_slot_id"]}
        for r in ordered
    ]
    assigned = optimal_lineup(lineup_input, slot_counts or {})
    suggested = [_lineup_row(slot, row) for slot in sorted(assigned) for row in assigned[slot]]

    current_ids = {r["player_id"] for r in starters}
    suggested_ids = {r["player_id"] for r in suggested}
    current_total = round(sum(r["projected"] or 0 for r in starters), 2)
    suggested_total = round(sum(r["projected"] or 0 for r in suggested), 2)
    by_pid = {r["player_id"]: r for r in ordered}
    sit = [
        {"slot": r["slot"], "player_id": r["player_id"], "name": r["name"], "projected": r["projected"]}
        for r in starters if r["player_id"] not in suggested_ids
    ]
    start = [r for r in suggested if r["player_id"] not in current_ids]

    public_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in ordered]
    return {
        "week": week,
        "players": public_rows,
        "current_total": current_total,
        "suggested_lineup": suggested,
        "suggested_total": suggested_total,
        "changes": {"start": start, "sit": sit, "gain": round(suggested_total - current_total, 2)},
    }
```
(`by_pid` is unused — remove it if a linter complains; keep the code otherwise.)

- [ ] **Step 4: implement `server.py`.** Imports: add `player_ids_filter` to the filters import; `shape_projections` to the shapes import. Add a schedules cache next to the index cache:
```python
_pro_schedules: dict[str, Any] | None = None


def _get_pro_schedules(client: EspnClient) -> dict[str, Any]:
    """ESPN's NFL schedule/bye table, fetched once per process."""
    global _pro_schedules
    if _pro_schedules is None:
        _pro_schedules = client.get_pro_schedules()
    return _pro_schedules


def set_pro_schedules_for_tests(schedules: dict[str, Any] | None) -> None:
    global _pro_schedules
    _pro_schedules = schedules
```
Tool, placed after `get_matchup`:
```python
MAX_WEEK = 18


@mcp.tool
def get_projections(week: int | None = None) -> dict[str, Any]:
    """ESPN projections for the user's roster for one NFL week, with a suggested optimal lineup.

    Use this for "set my lineup", "start X or Y?", or "who's on bye?". week
    defaults to the current NFL week; once this week's games have started,
    pass next week's number to plan ahead (projections exist as soon as ESPN
    publishes them, usually the Tuesday before).

    players: every rostered player with slot (current lineup slot), opponent
    ("@KC" away, "vs KC" home, "BYE"), kickoff (UTC), and projected (ESPN's
    points projection for that week; null if ESPN has none). suggested_lineup
    fills this league's starting slots (including FLEX-type slots and their
    eligibility rules) to maximize projected points; players on IR are never
    moved. changes lists who to start and who to sit to get there, with the
    projected gain. Present changes to the user rather than the whole table
    when they ask for lineup advice.
    """
    if week is not None and not 1 <= week <= MAX_WEEK:
        raise ToolError(f"week must be between 1 and {MAX_WEEK} (got {week}).")
    try:
        client = _get_client()
        league = client.get("mRoster", "mSettings")
        team_id = client.find_my_team_id(league)
        entries = (team_by_id(league, team_id).get("roster") or {}).get("entries") or []
        counts = {
            int(slot): count
            for slot, count in ((league.get("settings") or {}).get("rosterSettings") or {})
            .get("lineupSlotCounts", {})
            .items()
        }
        target_week = week or league.get("scoringPeriodId") or 1
        ids_ = [e.get("playerId") for e in entries if e.get("playerId") is not None]
        proj = client.get(
            "kona_player_info", fantasy_filter=player_ids_filter(ids_), scoring_period=target_week
        )
        schedules = _get_pro_schedules(client)
        return shape_projections(target_week, entries, proj.get("players") or [], schedules, counts)
    except (FilterError, EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e
```
INSTRUCTIONS: replace `Call get_league_settings before start/sit, pickup, or trade advice so\nrecommendations use this league's scoring (PPR or not) and roster limits;\nits result is stable for the season, so one call per conversation is enough.` with:
```
For start/sit or "set my lineup", call get_projections (pass next week's
number once this week's games have started) and present its changes; it
already applies this league's lineup slots. Call get_league_settings before
pickup or trade advice so recommendations use this league's scoring (PPR or
not) and roster limits; its result is stable for the season, so one call per
conversation is enough.
```
and update the tool list sentence to name seven tools (`whoami, get_league_settings, get_my_team, get_matchup, get_projections, get_free_agents, and get_player`).
README `## Tools`: add after `get_matchup`: ``- `get_projections` — this (or any) week's ESPN projections for your roster with opponent/bye/kickoff, plus a suggested optimal lineup and the start/sit changes to reach it.``

- [ ] **Step 5:** `uv run pytest -q` → all pass (report the number); stdio check OK.
- [ ] **Step 6:** Commit `feat: add get_projections tool with suggested lineup`.

---

### Task 3: Live check (controller)
- [ ] `get_projections(week=2)` live: opponents/kickoffs plausible, suggested lineup legal (1 QB, 2 RB, 2 WR, TE, FLEX, D/ST, K), changes sensible.
