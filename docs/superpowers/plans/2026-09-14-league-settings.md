# `get_league_settings` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose league scoring, roster, schedule, waiver, and trade rules as `get_league_settings()`.

**Architecture:** `stats.py` gains scoring-item names; `shapes.py` gains `shape_league_settings(league)`; `server.py` gains the tool + INSTRUCTIONS line. One ESPN call (`mSettings`).

**Spec:** `docs/superpowers/specs/2026-09-14-league-settings-design.md` — read the "Verified facts" and "Changes" sections; they are the authority.

Fixture `tests/fixtures/league_settings.json` is already on disk and committed (`settings.name` "Test League", size 12, real scoring items, lineup counts, limits, schedule, waivers, trades with `deadlineDate` 1796230800000 → `2026-12-02`).

---

### Task 1: scoring names + `shape_league_settings`

**Files:** `src/fantasy_mcp/stats.py`, `src/fantasy_mcp/shapes.py`, `tests/conftest.py`, `tests/test_stats.py`, `tests/test_shapes.py`

- [ ] **Step 1: conftest fixture** — append to `tests/conftest.py`:
```python


@pytest.fixture
def league_settings_json() -> dict:
    return json.loads((FIXTURES / "league_settings.json").read_text())
```

- [ ] **Step 2: failing tests.** Append to `tests/test_stats.py` (extend its import to include `scoring_name`):
```python
def test_scoring_name_known_alias_and_unknown():
    assert scoring_name(53) == "receptions"
    assert scoring_name(198) == "fg_made_50_plus"
    assert scoring_name(130) == "dst_yards_allowed_200_299"
    assert scoring_name(63) == "stat_63"
```
Append to `tests/test_shapes.py`:
```python
def test_shape_league_settings_from_fixture(league_settings_json):
    out = shapes.shape_league_settings(league_settings_json)
    assert out["league_name"] == "Test League"
    assert out["size"] == 12
    assert out["is_public"] is False

    scoring = out["scoring"]
    assert scoring["type"] == "H2H_POINTS"
    assert scoring["ppr"] == 1
    rules = scoring["rules"]
    assert rules["pass_yds"] == 0.04 and rules["pass_td"] == 4 and rules["pass_int"] == -2
    assert rules["rush_yds"] == 0.1 and rules["rec_yds"] == 0.1 and rules["receptions"] == 1
    assert rules["fg_made_50_plus"] == 5 and rules["fg_missed"] == -1
    assert rules["dst_sacks"] == 1 and rules["dst_int"] == 2          # from pointsOverrides["16"]
    assert rules["dst_yards_allowed_200_299"] == 2 and rules["dst_yards_allowed_550_plus"] == -7
    assert rules["stat_63"] == 6                                       # unmapped id kept honestly
    assert "team_win" not in rules                                     # zero-point items dropped
    assert scoring["summary"] == (
        "Full PPR · 25 pass yds/pt · 10 rush/rec yds/pt · 4-pt pass TD · 6-pt rush/rec TD · -2 INT · -2 fumble lost"
    )

    roster = out["roster"]
    assert roster["lineup"] == {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "D/ST": 1, "K": 1, "BENCH": 7, "IR": 1, "FLEX": 1}
    assert list(roster["lineup"]) == ["QB", "RB", "WR", "TE", "D/ST", "K", "BENCH", "IR", "FLEX"]  # slot-id order
    assert roster["position_limits"] == {"QB": 4, "RB": 8, "WR": 8, "TE": 3, "K": 3, "D/ST": 3}
    assert roster["move_limit"] is None
    assert roster["lineup_lock"] == "INDIVIDUAL_GAME"

    assert out["schedule"] == {
        "regular_season_weeks": 14, "matchup_weeks_per_period": 1, "playoff_teams": 6,
        "playoff_seeding": "TOTAL_POINTS_SCORED", "current_week": 1, "final_week": 17,
    }
    assert out["waivers"] == {
        "type": "WAIVERS_TRADITIONAL", "budget": 100, "min_bid": 1, "waiver_hours": 24,
        "order_resets": True,
        "process_days": ["MONDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"],
    }
    assert out["trades"] == {"deadline": "2026-12-02", "review_hours": 24, "veto_votes_required": 5}


def test_shape_league_settings_sparse():
    out = shapes.shape_league_settings({})
    assert out["league_name"] is None and out["size"] is None
    assert out["scoring"] == {"type": None, "ppr": 0, "rules": {}, "summary": "Standard (no PPR)"}
    assert out["roster"] == {"lineup": {}, "position_limits": {}, "move_limit": None, "lineup_lock": None}
    assert out["trades"]["deadline"] is None


def test_scoring_summary_half_ppr_and_split_rules():
    league = {"settings": {"scoringSettings": {"scoringItems": [
        {"statId": 53, "points": 0.5}, {"statId": 24, "points": 0.1}, {"statId": 42, "points": 0.2},
        {"statId": 25, "points": 6}, {"statId": 43, "points": 4}, {"statId": 20, "points": -1},
    ]}}}
    summary = shapes.shape_league_settings(league)["scoring"]["summary"]
    assert summary == "Half PPR · 10 rush yds/pt · 5 rec yds/pt · 6-pt rush TD · 4-pt rec TD · -1 INT"
```

- [ ] **Step 3:** `uv run pytest tests/test_stats.py tests/test_shapes.py -q -k "scoring or league_settings"` → failures (import/attribute errors).

- [ ] **Step 4: implement `stats.py`** — append:
```python
# Scoring-item ids (league settings) that don't appear in game logs, verified live.
SCORING_STAT_NAMES: dict[int, str] = {
    **STAT_NAMES,
    198: "fg_made_50_plus",
    89: "dst_points_allowed_0",
    90: "dst_points_allowed_1_6",
    91: "dst_points_allowed_7_13",
    92: "dst_points_allowed_14_17",
    123: "dst_points_allowed_28_34",
    124: "dst_points_allowed_35_45",
    125: "dst_points_allowed_46_plus",
    128: "dst_yards_allowed_under_100",
    129: "dst_yards_allowed_100_199",
    130: "dst_yards_allowed_200_299",
    131: "dst_yards_allowed_300_349",
    132: "dst_yards_allowed_350_399",
    133: "dst_yards_allowed_400_449",
    134: "dst_yards_allowed_450_499",
    135: "dst_yards_allowed_500_549",
    136: "dst_yards_allowed_550_plus",
}


def scoring_name(stat_id: int) -> str:
    """Name for a league scoring item; unmapped ids become ``stat_<id>`` rather than a guess."""
    return SCORING_STAT_NAMES.get(stat_id, f"stat_{stat_id}")
```

- [ ] **Step 5: implement `shapes.py`.** Change the stats import to `from fantasy_mcp.stats import scoring_name, shape_stat_line`, add `import datetime as dt` to the stdlib imports, and append:
```python
DST_POSITION_ID = 16


def _num(value: Any) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _scoring_rules(items: list[dict[str, Any]]) -> dict[str, int | float]:
    rules: dict[str, int | float] = {}
    for item in items or []:
        points = item.get("points") or 0
        if not points:
            points = (item.get("pointsOverrides") or {}).get(str(DST_POSITION_ID)) or 0
        if points and item.get("statId") is not None:
            rules[scoring_name(int(item["statId"]))] = _num(points)
    return rules


def _per_point(points: int | float) -> int | float:
    return _num(round(1 / points)) if points else 0


def _scoring_summary(rules: dict[str, int | float]) -> str:
    parts: list[str] = []
    ppr = rules.get("receptions", 0)
    parts.append(
        "Full PPR" if ppr == 1 else "Half PPR" if ppr == 0.5 else f"{ppr} PPR" if ppr else "Standard (no PPR)"
    )
    if rules.get("pass_yds"):
        parts.append(f"{_per_point(rules['pass_yds'])} pass yds/pt")
    rush_y, rec_y = rules.get("rush_yds"), rules.get("rec_yds")
    if rush_y and rush_y == rec_y:
        parts.append(f"{_per_point(rush_y)} rush/rec yds/pt")
    else:
        if rush_y:
            parts.append(f"{_per_point(rush_y)} rush yds/pt")
        if rec_y:
            parts.append(f"{_per_point(rec_y)} rec yds/pt")
    if rules.get("pass_td"):
        parts.append(f"{rules['pass_td']}-pt pass TD")
    rush_td, rec_td = rules.get("rush_td"), rules.get("rec_td")
    if rush_td and rush_td == rec_td:
        parts.append(f"{rush_td}-pt rush/rec TD")
    else:
        if rush_td:
            parts.append(f"{rush_td}-pt rush TD")
        if rec_td:
            parts.append(f"{rec_td}-pt rec TD")
    if rules.get("pass_int"):
        parts.append(f"{rules['pass_int']} INT")
    if rules.get("fumbles_lost"):
        parts.append(f"{rules['fumbles_lost']} fumble lost")
    return " · ".join(parts)


def _epoch_ms_date(value: Any) -> str | None:
    if not value:
        return None
    return dt.datetime.fromtimestamp(int(value) / 1000, dt.timezone.utc).date().isoformat()


def _unlimited_to_none(value: Any) -> Any:
    return None if value is None or value == -1 else value


def shape_league_settings(league: dict[str, Any]) -> dict[str, Any]:
    """Shape an ``mSettings`` payload into scoring, roster, schedule, waiver, and trade rules."""
    settings = league.get("settings") or {}
    roster = settings.get("rosterSettings") or {}
    scoring = settings.get("scoringSettings") or {}
    schedule = settings.get("scheduleSettings") or {}
    waivers = settings.get("acquisitionSettings") or {}
    trades = settings.get("tradeSettings") or {}
    status = league.get("status") or {}

    rules = _scoring_rules(scoring.get("scoringItems") or [])
    lineup = {
        ids.name(ids.LINEUP_SLOTS, int(slot)): count
        for slot, count in sorted((roster.get("lineupSlotCounts") or {}).items(), key=lambda kv: int(kv[0]))
        if count
    }
    limits = {
        ids.name(ids.POSITIONS, int(pos)): limit
        for pos, limit in sorted((roster.get("positionLimits") or {}).items(), key=lambda kv: int(kv[0]))
        if limit is not None and limit >= 0
    }
    return {
        "league_name": settings.get("name"),
        "size": settings.get("size"),
        "is_public": settings.get("isPublic"),
        "scoring": {
            "type": scoring.get("scoringType"),
            "ppr": rules.get("receptions", 0),
            "rules": rules,
            "summary": _scoring_summary(rules),
        },
        "roster": {
            "lineup": lineup,
            "position_limits": limits,
            "move_limit": _unlimited_to_none(roster.get("moveLimit")),
            "lineup_lock": roster.get("lineupLocktimeType"),
        },
        "schedule": {
            "regular_season_weeks": schedule.get("matchupPeriodCount"),
            "matchup_weeks_per_period": schedule.get("matchupPeriodLength"),
            "playoff_teams": schedule.get("playoffTeamCount"),
            "playoff_seeding": schedule.get("playoffSeedingRule"),
            "current_week": status.get("currentMatchupPeriod"),
            "final_week": status.get("finalScoringPeriod"),
        },
        "waivers": {
            "type": waivers.get("acquisitionType"),
            "budget": waivers.get("acquisitionBudget"),
            "min_bid": waivers.get("minimumBid"),
            "waiver_hours": waivers.get("waiverHours"),
            "order_resets": waivers.get("waiverOrderReset"),
            "process_days": waivers.get("waiverProcessDays") or [],
        },
        "trades": {
            "deadline": _epoch_ms_date(trades.get("deadlineDate")),
            "review_hours": trades.get("revisionHours"),
            "veto_votes_required": trades.get("vetoVotesRequired"),
        },
    }
```

- [ ] **Step 6:** `uv run pytest -q` → `130 passed`. If the fixture lineup order or a rule value differs from the test, print the actual output and report it — do not edit the fixture.
- [ ] **Step 7:** Commit `feat: shape league scoring, roster, schedule, waiver and trade settings`.

---

### Task 2: tool + instructions + README

**Files:** `src/fantasy_mcp/server.py`, `tests/test_server.py`, `README.md`

- [ ] **Step 1: failing tests** — append to `tests/test_server.py`:
```python
@respx.mock
async def test_get_league_settings_tool(client, league_settings_json):
    route = respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_settings_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool("get_league_settings", {})
    assert result.data["league_name"] == "Test League"
    assert result.data["scoring"]["ppr"] == 1
    assert result.data["roster"]["lineup"]["FLEX"] == 1
    assert route.calls.last.request.url.params.get_list("view") == ["mSettings"]


async def test_six_tools_registered(client):
    async with Client(server.mcp) as c:
        names = sorted(t.name for t in await c.list_tools())
    assert names == ["get_free_agents", "get_league_settings", "get_matchup", "get_my_team", "get_player", "whoami"]
```
- [ ] **Step 2:** run → 2 FAIL (unknown tool / name list).
- [ ] **Step 3: implement.** Add `shape_league_settings` to the `fantasy_mcp.shapes` import list in `server.py`. Add after `whoami` (keep tool order: whoami, get_league_settings, get_my_team, ...):
```python
@mcp.tool
def get_league_settings() -> dict[str, Any]:
    """League rules: scoring, roster construction, schedule/playoffs, waivers, trades.

    Call this before start/sit, pickup, or trade advice so recommendations use
    this league's scoring (scoring.ppr = points per reception; scoring.summary
    is a one-line description; scoring.rules maps stat names -- the same names
    get_player's game log uses -- to points, with unmapped ESPN ids as stat_<id>).
    roster.lineup gives starting slots and bench/IR counts; roster.position_limits
    caps how many of a position a team may roster. waivers describes the claim
    system (budget is FAAB dollars when present); trades.deadline is a UTC date.
    """
    try:
        client = _get_client()
        return shape_league_settings(client.get("mSettings"))
    except (EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e
```
INSTRUCTIONS: replace the sentence starting `Use get_player for` paragraph's tool list line so it reads `Only whoami, get_league_settings, get_my_team, get_matchup, get_free_agents, and get_player exist.` and add, before "Nothing here can modify the team.", a paragraph:
```
Call get_league_settings before start/sit, pickup, or trade advice so
recommendations use this league's scoring (PPR or not) and roster limits;
its result is stable for the season, so one call per conversation is enough.
```
README `## Tools`: add after the `whoami` bullet: ``- `get_league_settings` — scoring rules (with a one-line summary), lineup slots, position limits, playoff format, waiver and trade rules.``
- [ ] **Step 4:** `uv run pytest -q` → `132 passed`; stdio check OK.
- [ ] **Step 5:** Commit `feat: add get_league_settings tool`.

---

### Task 3: Live check (controller)
- [ ] Call `get_league_settings` live; confirm summary reads "Full PPR · 25 pass yds/pt · 10 rush/rec yds/pt · 4-pt pass TD · 6-pt rush/rec TD · -2 INT · -2 fumble lost", lineup/limits match ESPN's league settings page, deadline 2026-12-02.
