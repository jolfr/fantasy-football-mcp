# `compare_players` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `compare_players(players, week)` — compact side-by-side rows for 2–6 players, with per-input error reporting.

**Architecture:** Small extensions to `filters.py` (list of ids), `players.py` (batch resolution with error collection), `shapes.py` (`shape_comparison` built from card helpers + `game_context`), and one tool in `server.py`.

**Spec:** `docs/superpowers/specs/2026-09-14-compare-players-design.md` (authoritative; read it in full — fixture facts and every field rule are there).

---

### Task 1: filters + players + shapes

**Files:** `src/fantasy_mcp/filters.py`, `src/fantasy_mcp/players.py`, `src/fantasy_mcp/shapes.py`, `tests/conftest.py`, `tests/test_filters.py`, `tests/test_players.py`, `tests/test_shapes.py`

- [ ] **Step 1: conftest** — append a `compare_json` fixture loading `compare.json`.

- [ ] **Step 2: failing tests.**

`tests/test_filters.py`:
```python
def test_player_card_filter_accepts_a_list_of_ids():
    out = player_card_filter([4242335, 4361370], season=2026)
    assert out["players"]["filterIds"] == {"value": [4242335, 4361370]}
    assert player_card_filter(4242335, season=2026)["players"]["filterIds"] == {"value": [4242335]}
```
`tests/test_players.py` (add `resolve_players` to the import):
```python
def test_resolve_players_mixed_inputs_preserve_order_and_collect_errors(players_index):
    ids, unresolved = resolve_players(["kraft", 4242335, "tucker", "Nobody Real", "4242335", "A.J. Brown"], players_index)
    assert ids == [4572680, 4242335, 1001]           # duplicates dropped, order kept
    assert [u["input"] for u in unresolved] == ["tucker", "Nobody Real"]
    assert "id 4572680" in unresolved[0]["error"]
    assert "No active player matches" in unresolved[1]["error"]


def test_resolve_players_empty_and_blank():
    ids, unresolved = resolve_players(["", " "], [])
    assert ids == [] and len(unresolved) == 2
```
`tests/test_shapes.py`:
```python
def test_shape_comparison_rows(compare_json, pro_schedules_json):
    ordered = [next(p for p in compare_json["players"] if p["id"] == pid) for pid in (4242335, 4361370)]
    rows = shapes.shape_comparison(ordered, compare_json, 2, pro_schedules_json)
    assert [r["name"] for r in rows] == ["Compare Back", "Compare Receiver"]
    back = rows[0]
    assert back == {
        "player_id": 4242335, "name": "Compare Back", "position": "RB", "pro_team": "IND",
        "injury_status": "ACTIVE", "league_status": "ONTEAM", "owned_by": "My Matchup Team",
        "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4242335.png&w=350&h=254",
        "week": {"projected": 17.68, "opponent": "@KC", "kickoff": "2026-09-21T00:20:00Z"},
        "season": {"projected": 315.58, "points": 25.1, "positional_rank": 4, "games": 1, "avg": 25.1},
        "last_3": [25.1],
        "last_season": {"points": 362.3, "games": 4, "avg": 90.58},
        "percent_owned": 99.9, "percent_change": 0.0,
    }
    rec = rows[1]
    assert rec["league_status"] == "FREEAGENT" and rec["owned_by"] is None
    assert rec["week"] == {"projected": 15.55, "opponent": "@BAL", "kickoff": "2026-09-20T17:00:00Z"}
    assert rec["last_season"] == {"points": 268.0, "games": 3, "avg": 89.33}
    assert rec["last_3"] == [28.2]


def test_shape_comparison_unknown_id_and_no_last_season(compare_json, pro_schedules_json):
    entry = next(p for p in compare_json["players"] if p["id"] == 4242335)
    entry["player"]["stats"] = [s for s in entry["player"]["stats"] if s["seasonId"] == 2026]
    rows = shapes.shape_comparison([entry, {"id": 99, "error": "ESPN returned no player with id 99."}], compare_json, 2, {})
    assert rows[0]["last_season"] is None and rows[0]["week"]["opponent"] is None
    assert rows[1] == {"player_id": 99, "error": "ESPN returned no player with id 99."}
```

- [ ] **Step 3:** run → failures.

- [ ] **Step 4: implement.**

`filters.py` — change the signature and first line of `player_card_filter`:
```python
def player_card_filter(player_ids: int | list[int], *, season: int) -> dict[str, Any]:
    """Filter for player cards: season totals, last season, and weekly projections."""
    ids = [player_ids] if isinstance(player_ids, int) else list(player_ids)
    stat_ids = [f"00{season}", f"10{season}", f"00{season - 1}"]
    stat_ids += [f"11{season}{week}" for week in range(1, WEEKS_IN_SEASON + 1)]
    return {
        "players": {
            "filterIds": {"value": ids},
            "filterStatsForTopScoringPeriodIds": {"value": 17, "additionalValue": stat_ids},
        }
    }
```
`players.py` — append:
```python
def resolve_players(
    inputs: list[str | int], index: list[dict[str, Any]]
) -> tuple[list[int], list[dict[str, Any]]]:
    """Resolve a mixed list of ids / names. Returns (ids in input order, unresolved entries)."""
    ids: list[int] = []
    unresolved: list[dict[str, Any]] = []
    for raw in inputs:
        try:
            if isinstance(raw, int):
                player_id = raw
            elif isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
                player_id = int(raw.strip())
            else:
                player_id = resolve_player(str(raw), index)
        except EspnError as e:
            unresolved.append({"input": raw, "error": str(e)})
            continue
        if player_id not in ids:
            ids.append(player_id)
    return ids, unresolved
```
`shapes.py` — append:
```python
def _weekly_actuals(player: dict[str, Any], season: int) -> list[tuple[int, float]]:
    """(week, points) for this season's weekly actual entries, newest first."""
    rows = [
        (int(s.get("scoringPeriodId") or 0), float(s.get("appliedTotal") or 0.0))
        for s in player.get("stats") or []
        if s.get("seasonId") == season and s.get("statSourceId") == ACTUAL_SOURCE_ID
        and (s.get("scoringPeriodId") or 0) > 0
    ]
    return sorted(rows, key=lambda r: -r[0])


def _season_line(player: dict[str, Any], season: int) -> tuple[float | None, int, float | None]:
    points = _stat(player, period=SEASON_PERIOD, source=ACTUAL_SOURCE_ID, season=season)
    games = len(_weekly_actuals(player, season))
    avg = _round(points / games) if points is not None and games else None
    return points, games, avg


def shape_comparison(
    entries: list[dict[str, Any]], league: dict[str, Any], week: int, schedules: dict[str, Any]
) -> list[dict[str, Any]]:
    """Compact side-by-side rows for compare_players; entries with an ``error`` key pass through."""
    season = league.get("seasonId", -1)
    rows: list[dict[str, Any]] = []
    for entry in entries:
        if "error" in entry:
            rows.append({"player_id": entry.get("player_id", entry.get("id")), "error": entry["error"]})
            continue
        player = entry.get("player") or {}
        ownership = player.get("ownership") or {}
        player_id = entry.get("id", player.get("id"))
        position = ids.name(ids.POSITIONS, player.get("defaultPositionId", -1))
        pro_team = ids.name(ids.PRO_TEAMS, player.get("proTeamId", -1))
        team = _find_team(league, entry.get("onTeamId")) if entry.get("onTeamId") else None
        rank = ((entry.get("ratings") or {}).get("0") or {}).get("positionalRanking") or None
        context = game_context(schedules, player.get("proTeamId"), week)
        points, games, avg = _season_line(player, season)
        last_points, last_games, last_avg = _season_line(player, season - 1)
        rows.append(
            {
                "player_id": player_id,
                "name": player.get("fullName"),
                "position": position,
                "pro_team": pro_team,
                "injury_status": player.get("injuryStatus"),
                "league_status": entry.get("status"),
                "owned_by": team.get("name") if team else None,
                "headshot_url": headshot_url(player_id, position, pro_team),
                "week": {
                    "projected": _stat(player, period=week, source=PROJECTION_SOURCE_ID, season=season),
                    "opponent": context["opponent"],
                    "kickoff": context["kickoff"],
                },
                "season": {
                    "projected": _stat(player, period=SEASON_PERIOD, source=PROJECTION_SOURCE_ID, season=season),
                    "points": points,
                    "positional_rank": rank,
                    "games": games,
                    "avg": avg,
                },
                "last_3": [_round(p) for _, p in _weekly_actuals(player, season)[:3]],
                "last_season": (
                    {"points": last_points, "games": last_games, "avg": last_avg}
                    if last_points is not None
                    else None
                ),
                "percent_owned": _round(ownership.get("percentOwned"), ndigits=1),
                "percent_change": _round(ownership.get("percentChange"), ndigits=1),
            }
        )
    return rows
```

- [ ] **Step 5:** `uv run pytest -q` → 182 + 1 + 2 + 2 = 187 passed.
- [ ] **Step 6:** Commit `feat: batch player resolution and comparison rows`.

---

### Task 2: tool

**Files:** `src/fantasy_mcp/server.py`, `tests/test_server.py`, `README.md`

- [ ] **Step 1: failing tests** — `tests/test_server.py`:
```python
@respx.mock
async def test_compare_players_tool(client, cached_index, cached_schedules, compare_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=compare_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("compare_players", {"players": ["Jonathan Taylor", "4361370"], "week": 2})
    req = route.calls.last.request
    assert req.url.params.get_list("view") == ["kona_playercard", "mTeam", "mStatus"]
    assert req.url.params["scoringPeriodId"] == "2"
    assert json.loads(req.headers["x-fantasy-filter"])["players"]["filterIds"]["value"] == [4242335, 4361370]
    assert [p["name"] for p in result.data["players"]] == ["Compare Back", "Compare Receiver"]
    assert result.data["players"][0]["week"]["projected"] == 17.68
    assert "unresolved" not in result.data


@respx.mock
async def test_compare_players_default_week_reads_status_first(client, cached_index, cached_schedules, compare_json):
    def respond(request):
        views = request.url.params.get_list("view")
        if views == ["mStatus"]:
            return httpx.Response(200, json={"status": {"currentMatchupPeriod": 1}})
        return httpx.Response(200, json=compare_json)

    route = respx.get(LEAGUE_URL).mock(side_effect=respond)
    async with Client(server.mcp) as c:
        result = await c.call_tool("compare_players", {"players": [4242335, 4361370]})
    assert result.data["week"] == 1
    assert route.calls[0].request.url.params.get_list("view") == ["mStatus"]
    assert route.calls[1].request.url.params["scoringPeriodId"] == "1"


@respx.mock
async def test_compare_players_partial_resolution(client, cached_index, cached_schedules, compare_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=compare_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("compare_players", {"players": ["Jonathan Taylor", "tucker"], "week": 2})
    assert [p["name"] for p in result.data["players"]] == ["Compare Back"]
    assert result.data["unresolved"][0]["input"] == "tucker"
    assert "id 4572680" in result.data["unresolved"][0]["error"]


@respx.mock
@pytest.mark.parametrize("players", [["a"], ["a", "b", "c", "d", "e", "f", "g"]])
async def test_compare_players_count_validation(client, players):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="between 2 and 6"):
            await c.call_tool("compare_players", {"players": players})
    assert not route.called


@respx.mock
async def test_compare_players_all_unresolved_is_tool_error(client, cached_index):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json={}))
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="Nobody Real"):
            await c.call_tool("compare_players", {"players": ["Nobody Real", "Nobody Else"], "week": 2})
    assert not route.called


async def test_nine_tools_registered(client):
    async with Client(server.mcp) as c:
        names = sorted(t.name for t in await c.list_tools())
    assert names == ["compare_players", "get_free_agents", "get_league_settings", "get_matchup", "get_my_team",
                     "get_player", "get_projections", "get_standings", "whoami"]
```
Delete `test_eight_tools_registered`.

- [ ] **Step 2:** run → failures.
- [ ] **Step 3: implement.** Imports: `resolve_players` from `fantasy_mcp.players`; `shape_comparison` from shapes. Add after `get_player`:
```python
MAX_COMPARE = 6


@mcp.tool
def compare_players(players: list[str | int], week: int | None = None) -> dict[str, Any]:
    """Compare 2-6 players side by side for "X or Y?" decisions.

    players may mix names and player_ids (ids from other tools are precise;
    names are matched against ESPN's active-player index). Ambiguous or
    unknown names are returned in `unresolved` with candidate ids -- retry
    just those, the rest still come back. week defaults to the league's
    current NFL week; pass next week's number to plan ahead.

    Each row: identity/status/owned_by; week {projected, opponent, kickoff};
    season {projected, points, positional_rank, games, avg}; last_3 (points in
    the most recent games this season, newest first); last_season {points,
    games, avg} or null; percent_owned / percent_change (ESPN-wide ownership
    and trend). Rows keep the input order.
    """
    if not 2 <= len(players) <= MAX_COMPARE:
        raise ToolError(f"Pass between 2 and {MAX_COMPARE} players (got {len(players)}).")
    if week is not None and not 1 <= week <= MAX_WEEK:
        raise ToolError(f"week must be between 1 and {MAX_WEEK} (got {week}).")
    try:
        client = _get_client()
        index = _get_players_index(client) if any(not isinstance(p, int) and not str(p).strip().lstrip("-").isdigit() for p in players) else []
        ids_, unresolved = resolve_players(players, index)
        if not ids_:
            raise EspnError("No players could be resolved: " + "; ".join(u["error"] for u in unresolved))
        if week is None:
            status = client.get("mStatus")
            week = (status.get("status") or {}).get("currentMatchupPeriod")
            if week is None:
                raise EspnError("ESPN response is missing status.currentMatchupPeriod.")
        league = client.get(
            "kona_playercard", "mTeam", "mStatus",
            fantasy_filter=player_card_filter(ids_, season=client.settings.season),
            scoring_period=week,
        )
        by_id = {e.get("id"): e for e in league.get("players") or []}
        ordered = [by_id.get(pid) or {"id": pid, "error": f"ESPN returned no player with id {pid}."} for pid in ids_]
        result: dict[str, Any] = {
            "week": week,
            "players": shape_comparison(ordered, league, week, _get_pro_schedules(client)),
        }
        if unresolved:
            result["unresolved"] = unresolved
        return result
    except (FilterError, EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e
```
INSTRUCTIONS: add "For 'X or Y?' questions call compare_players with all the names at once rather than get_player repeatedly." and list nine tools (add `compare_players` after `get_player`). README: bullet after `get_player`: ``- `compare_players` — 2–6 players side by side: this week's projection and opponent, season pace, recent form, last season, league availability, ownership trend.``

- [ ] **Step 4:** `uv run pytest -q` → 187 + 6 (one parametrized ×2) − 1 = 193 passed; stdio OK.
- [ ] **Step 5:** Commit `feat: add compare_players tool`.

### Task 3: Live check (controller)
- [ ] `compare_players(["Jonathan Taylor", "Chris Olave", "tucker"], week=2)`.
