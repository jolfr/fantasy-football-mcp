# `get_standings` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `get_standings()` — ranked league standings with records, points, streaks, projected finish, waiver priority, transactions, clinch status, and the user's team flagged.

**Architecture:** One pure shaper `shape_standings(league, my_team_id)` in `shapes.py`; one tool in `server.py` making a single `mTeam`+`mStandings`+`mSettings` call.

**Spec:** `docs/superpowers/specs/2026-09-14-standings-design.md` (authoritative). Fixture `tests/fixtures/standings.json` committed: teams (id, seed) = (12,1) "My Standings Team"/MST owner `{ABC-123}` → member Alex Owner, record 2-0-0 PF 231.5 PA 190.2 streak WIN 2, projected 3, waiver 5, transactions 1/1/0/faab 12, clinch NONE; (5,2) "Rival One" owner `{DEF-456}` → member with displayName "espnfan2" only, clinch CLINCHED_PLAYOFFS; (7,3) "Rival Two" owner `{GHI-789}` → firstName "Casey", lastName ""; (3,4) "Rival Three" no owners, 0-2-0 LOSS 2. `settings.scheduleSettings.playoffTeamCount 6`, `playoffSeedingRule TOTAL_POINTS_SCORED`, `seasonId 2026`, `status.currentMatchupPeriod 1`.

---

### Task 1: `shape_standings` + tool

**Files:** `src/fantasy_mcp/shapes.py`, `src/fantasy_mcp/server.py`, `tests/conftest.py`, `tests/test_shapes.py`, `tests/test_server.py`, `README.md`

- [ ] **Step 1: conftest** — append a `standings_json` fixture loading `standings.json` (same style as the others).

- [ ] **Step 2: failing tests.** `tests/test_shapes.py`:
```python
def test_shape_standings_rows_and_order(standings_json):
    out = shapes.shape_standings(standings_json, my_team_id=12)
    assert {k: out[k] for k in ("season", "week", "playoff_teams", "playoff_seeding")} == {
        "season": 2026, "week": 1, "playoff_teams": 6, "playoff_seeding": "TOTAL_POINTS_SCORED",
    }
    assert [t["rank"] for t in out["teams"]] == [1, 2, 3, 4]
    assert [t["team_id"] for t in out["teams"]] == [12, 5, 7, 3]
    assert out["teams"][0] == {
        "rank": 1, "team_id": 12, "name": "My Standings Team", "abbrev": "MST", "owner": "Alex Owner",
        "is_me": True, "record": {"wins": 2, "losses": 0, "ties": 0},
        "points_for": 231.5, "points_against": 190.2, "streak": "W2", "games_back": 0.0,
        "projected_rank": 3, "waiver_priority": 5,
        "transactions": {"acquisitions": 1, "drops": 1, "trades": 0, "faab_spent": 12},
        "clinched": None,
    }
    by_id = {t["team_id"]: t for t in out["teams"]}
    assert by_id[5]["owner"] == "espnfan2" and by_id[5]["clinched"] == "CLINCHED_PLAYOFFS"
    assert by_id[7]["owner"] == "Casey" and by_id[7]["streak"] == "L1"
    assert by_id[3]["owner"] is None and by_id[3]["streak"] == "L2" and by_id[3]["games_back"] == 2.0
    assert [t["is_me"] for t in out["teams"]] == [True, False, False, False]


def test_shape_standings_unseeded_teams_sort_by_record_and_ranks_are_gapless(standings_json):
    for t in standings_json["teams"]:
        t["playoffSeed"] = 0
    out = shapes.shape_standings(standings_json, my_team_id=None)
    assert [t["team_id"] for t in out["teams"]] == [12, 5, 7, 3]   # 2-0 231.5, 2-0 220.0, 1-1, 0-2
    assert [t["rank"] for t in out["teams"]] == [1, 2, 3, 4]
    assert not any(t["is_me"] for t in out["teams"])


def test_shape_standings_zero_rank_fields_become_null(standings_json):
    standings_json["teams"][0]["currentProjectedRank"] = 0
    standings_json["teams"][0]["waiverRank"] = 0
    standings_json["teams"][0]["record"]["overall"]["streakType"] = "NONE"
    standings_json["teams"][0]["record"]["overall"]["streakLength"] = 0
    row = shapes.shape_standings(standings_json, my_team_id=12)["teams"][0]
    assert row["projected_rank"] is None and row["waiver_priority"] is None and row["streak"] is None


def test_shape_standings_sparse():
    assert shapes.shape_standings({}, my_team_id=1) == {
        "season": None, "week": None, "playoff_teams": None, "playoff_seeding": None, "teams": [],
    }
    row = shapes.shape_standings({"teams": [{"id": 9}]}, my_team_id=9)["teams"][0]
    assert row["rank"] == 1 and row["is_me"] is True and row["record"] == {"wins": 0, "losses": 0, "ties": 0}
    assert row["owner"] is None and row["transactions"] == {"acquisitions": 0, "drops": 0, "trades": 0, "faab_spent": 0}
```
`tests/test_server.py`:
```python
@respx.mock
async def test_get_standings_tool(client, standings_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=standings_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_standings", {})
    assert route.calls.last.request.url.params.get_list("view") == ["mTeam", "mStandings", "mSettings"]
    assert [t["is_me"] for t in result.data["teams"]] == [True, False, False, False]
    assert result.data["teams"][0]["owner"] == "Alex Owner"


@respx.mock
async def test_get_standings_without_a_matching_team_still_returns(settings, standings_json):
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=standings_json))
    server.set_client_for_tests(EspnClient(dataclasses.replace(settings, swid="{NOBODY}")))
    try:
        async with Client(server.mcp) as c:
            result = await c.call_tool("get_standings", {})
    finally:
        server.set_client_for_tests(None)
    assert len(result.data["teams"]) == 4 and not any(t["is_me"] for t in result.data["teams"])


async def test_eight_tools_registered(client):
    async with Client(server.mcp) as c:
        names = sorted(t.name for t in await c.list_tools())
    assert names == ["get_free_agents", "get_league_settings", "get_matchup", "get_my_team",
                     "get_player", "get_projections", "get_standings", "whoami"]
```
Delete `test_seven_tools_registered`.

- [ ] **Step 3:** run → failures.

- [ ] **Step 4: implement `shapes.py`** — append:
```python
def _owner_name(league: dict[str, Any], team: dict[str, Any]) -> str | None:
    owners = team.get("owners") or []
    if not owners:
        return None
    swid = str(owners[0]).lower()
    member = next((m for m in league.get("members") or [] if str(m.get("id", "")).lower() == swid), None)
    if not member:
        return None
    first, last = (member.get("firstName") or "").strip(), (member.get("lastName") or "").strip()
    if first and last:
        return f"{first} {last}"
    return first or member.get("displayName") or None


def _streak(overall: dict[str, Any]) -> str | None:
    kind, length = overall.get("streakType"), overall.get("streakLength") or 0
    if kind not in ("WIN", "LOSS") or not length:
        return None
    return f"{'W' if kind == 'WIN' else 'L'}{int(length)}"


def _standings_row(league: dict[str, Any], team: dict[str, Any], my_team_id: int | None) -> dict[str, Any]:
    overall = (team.get("record") or {}).get("overall") or {}
    counter = team.get("transactionCounter") or {}
    clinch = team.get("playoffClinchType")
    return {
        "rank": team.get("playoffSeed") or 0,  # re-numbered after sorting
        "team_id": team.get("id"),
        "name": team.get("name"),
        "abbrev": team.get("abbrev"),
        "owner": _owner_name(league, team),
        "is_me": team.get("id") == my_team_id,
        "record": {
            "wins": overall.get("wins", 0),
            "losses": overall.get("losses", 0),
            "ties": overall.get("ties", 0),
        },
        "points_for": _round(overall.get("pointsFor", 0.0)),
        "points_against": _round(overall.get("pointsAgainst", 0.0)),
        "streak": _streak(overall),
        "games_back": _round(overall.get("gamesBack", 0.0)),
        "projected_rank": team.get("currentProjectedRank") or None,
        "waiver_priority": team.get("waiverRank") or None,
        "transactions": {
            "acquisitions": counter.get("acquisitions", 0),
            "drops": counter.get("drops", 0),
            "trades": counter.get("trades", 0),
            "faab_spent": counter.get("acquisitionBudgetSpent", 0),
        },
        "clinched": clinch if clinch and clinch != "NONE" else None,
    }


def shape_standings(league: dict[str, Any], my_team_id: int | None) -> dict[str, Any]:
    """League standings ordered by playoff seed (then record), with the user's team flagged."""
    rows = [_standings_row(league, t, my_team_id) for t in league.get("teams") or []]
    rows.sort(
        key=lambda r: (
            r["rank"] == 0,  # seeded teams first
            r["rank"],
            -r["record"]["wins"],
            -(r["points_for"] or 0),
        )
    )
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    schedule = (league.get("settings") or {}).get("scheduleSettings") or {}
    return {
        "season": league.get("seasonId"),
        "week": (league.get("status") or {}).get("currentMatchupPeriod"),
        "playoff_teams": schedule.get("playoffTeamCount"),
        "playoff_seeding": schedule.get("playoffSeedingRule"),
        "teams": rows,
    }
```

- [ ] **Step 5: implement `server.py`.** Add `shape_standings` to the shapes import. Add after `get_league_settings`:
```python
@mcp.tool
def get_standings() -> dict[str, Any]:
    """League standings: rank, record, points for/against, streak, projected finish, waiver order.

    Use this for "where do I stand", "who's in the playoff picture", "who has
    the top waiver priority", or "who's been active on waivers/trades". Teams
    are ordered by ESPN's playoff seed; is_me marks the user's team; owner is
    the ESPN member name; projected_rank is ESPN's projected final standing;
    clinched is set once a team has clinched a playoff spot. Records and points
    update when ESPN finalizes each week (use get_matchup for live scores).
    """
    try:
        client = _get_client()
        league = client.get("mTeam", "mStandings", "mSettings")
        try:
            my_team_id: int | None = client.find_my_team_id(league)
        except EspnError:
            my_team_id = None  # standings are still useful without knowing which team is ours
        return shape_standings(league, my_team_id)
    except (EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e
```
INSTRUCTIONS: add a sentence "Use get_standings for records, rankings, the playoff picture, or waiver order." before the "Only ... exist." sentence, and list eight tools (`whoami, get_league_settings, get_standings, get_my_team, get_matchup, get_projections, get_free_agents, and get_player`). README `## Tools`: add after `get_league_settings`: ``- `get_standings` — every team's rank, record, points, streak, ESPN projected finish, waiver priority, transaction counts, and playoff clinch status.`` (wrap at ~80 cols).

- [ ] **Step 6:** `uv run pytest -q` → 176 + 4 + 3 − 1 = 182 passed; stdio OK.
- [ ] **Step 7:** Commit `feat: add get_standings tool`.

### Task 2: Live check (controller)
- [ ] `get_standings()` live: 12 teams, `is_me` on team 12, owner names populated where ESPN has them.
