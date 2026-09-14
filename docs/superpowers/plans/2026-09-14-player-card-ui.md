# Player Card UI (Prefab) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render `get_player` as a Prefab card in MCP-Apps clients while Claude keeps receiving the same JSON profile as text.

**Architecture:** New pure module `cards.py` turns the `get_player` profile dict into a `PrefabApp` (header with badges, metrics row, outlook, points line chart, paginated game-log table with a compact box-score line). `get_player` becomes `@mcp.tool(app=True)` and returns `ToolResult(content=<profile JSON>, structured_content=<PrefabApp>)`. Nothing else in the server changes.

**Tech Stack:** Python 3.12, uv, fastmcp 4.0.3 (`[apps]` extra), prefab-ui 0.20.2 (pinned), pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-player-card-ui-design.md`

---

## File structure

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | add `fastmcp[apps]`, pin `prefab-ui==0.20.2` |
| `src/fantasy_mcp/cards.py` | NEW — `stat_line(stats)`, `player_card(profile)` |
| `src/fantasy_mcp/server.py` | `get_player` → app tool returning `ToolResult` |
| `tests/test_cards.py` | NEW |
| `tests/test_server.py` | `get_player` tests read `content[0].text` |
| `README.md` | note on card rendering |

Notes for the engineer:
- Run everything via `uv run ...`. Current state: 99 tests pass on branch `feat/player-card-ui`.
- Serialize a `PrefabApp` in tests with `app.to_json()` → `{"$prefab": {...}, "view": {"type": "Div", "children": [...]}}`. Node keys are camelCase (`trendSentiment`, `dataKey`, `pageSize`, `xAxis`).
- Commit messages: Conventional Commits + the two trailer lines the controller gives you.

---

### Task 1: Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the apps extra and pin prefab-ui**

```bash
uv add "fastmcp[apps]>=4.0.3" "prefab-ui==0.20.2"
```

Then open `pyproject.toml` and confirm `dependencies` contains exactly (order may differ):
```toml
    "fastmcp[apps]>=4.0.3",
    "httpx>=0.28.1",
    "prefab-ui==0.20.2",
    "python-dotenv>=1.2.3",
```
(If `uv add` left a plain `"fastmcp>=4.0.3"` line alongside, remove it so only the `[apps]` one remains.)

- [ ] **Step 2: Verify**

Run: `uv sync && uv run python -c "import prefab_ui; from fastmcp.tools import ToolResult; print(prefab_ui.__version__)"`
Expected: `0.20.2`
Run: `uv run pytest -q` → `99 passed`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add fastmcp apps extra and pin prefab-ui"
```

---

### Task 2: `stat_line`

**Files:**
- Create: `src/fantasy_mcp/cards.py`
- Create: `tests/test_cards.py`

- [ ] **Step 1: Write the failing tests** — `tests/test_cards.py`:

```python
from fantasy_mcp.cards import stat_line


def test_qb_line():
    stats = {"pass_att": 34, "pass_comp": 18, "pass_yds": 164, "pass_td": 2, "rush_att": 5, "rush_yds": 31}
    assert stat_line(stats) == "18/34 164 yds 2 TD · 5 car 31 yds"


def test_qb_line_with_int():
    assert stat_line({"pass_comp": 20, "pass_att": 30, "pass_yds": 250, "pass_int": 1}) == "20/30 250 yds 1 INT"


def test_rb_line():
    stats = {
        "rush_att": 19, "rush_yds": 98, "rush_td": 2,
        "receptions": 3, "rec_yds": 23, "targets": 4,
        "fumbles": 1, "fumbles_lost": 1,
    }
    assert stat_line(stats) == "19 car 98 yds 2 TD · 3 rec 23 yds (4 tgt) · 1 fum lost"


def test_wr_line():
    assert stat_line({"receptions": 10, "rec_yds": 182, "targets": 13}) == "10 rec 182 yds (13 tgt)"


def test_wr_line_with_td_no_targets():
    assert stat_line({"receptions": 4, "rec_yds": 60, "rec_td": 1}) == "4 rec 60 yds 1 TD"


def test_kicker_line():
    assert stat_line({"fg_made": 2, "fg_att": 2, "xp_made": 5, "xp_att": 5}) == "FG 2/2 XP 5/5"


def test_kicker_line_made_only():
    assert stat_line({"fg_made": 1, "xp_made": 3}) == "FG 1 XP 3"


def test_dst_line():
    stats = {"dst_sacks": 2, "dst_int": 1, "dst_fumble_rec": 1, "dst_points_allowed": 23, "dst_yards_allowed": 251}
    assert stat_line(stats) == "2 sk 1 int 1 fr 23 pts 251 yds allowed"


def test_dst_line_touchdown_and_block():
    assert stat_line({"dst_blocked_kicks": 1, "dst_int_return_td": 1, "dst_points_allowed": 0}) == "1 blk 1 TD 0 pts allowed"


def test_empty_and_unknown_only():
    assert stat_line({}) == ""
    assert stat_line({"games_played": 1, "team_win": 1}) == ""


def test_numbers_render_without_trailing_zero():
    assert stat_line({"rush_att": 5.0, "rush_yds": 31.0}) == "5 car 31 yds"
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_cards.py -v` → `ModuleNotFoundError: No module named 'fantasy_mcp.cards'`

- [ ] **Step 3: Create `src/fantasy_mcp/cards.py`** with the formatter (the card builder is added in Task 3):

```python
"""Prefab UI for player cards: pure functions from tool output to a PrefabApp."""

from __future__ import annotations

from typing import Any

Stats = dict[str, int | float]


def _n(value: Any) -> str:
    """Render a stat number without a trailing .0."""
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def _passing(s: Stats) -> str | None:
    if not any(k in s for k in ("pass_comp", "pass_att", "pass_yds", "pass_td", "pass_int")):
        return None
    parts: list[str] = []
    if "pass_comp" in s and "pass_att" in s:
        parts.append(f"{_n(s['pass_comp'])}/{_n(s['pass_att'])}")
    if "pass_yds" in s:
        parts.append(f"{_n(s['pass_yds'])} yds")
    if s.get("pass_td"):
        parts.append(f"{_n(s['pass_td'])} TD")
    if s.get("pass_int"):
        parts.append(f"{_n(s['pass_int'])} INT")
    return " ".join(parts) or None


def _rushing(s: Stats) -> str | None:
    if not any(k in s for k in ("rush_att", "rush_yds", "rush_td")):
        return None
    parts = []
    if "rush_att" in s:
        parts.append(f"{_n(s['rush_att'])} car")
    if "rush_yds" in s:
        parts.append(f"{_n(s['rush_yds'])} yds")
    if s.get("rush_td"):
        parts.append(f"{_n(s['rush_td'])} TD")
    return " ".join(parts) or None


def _receiving(s: Stats) -> str | None:
    if not any(k in s for k in ("receptions", "targets", "rec_yds", "rec_td")):
        return None
    parts = []
    if "receptions" in s:
        parts.append(f"{_n(s['receptions'])} rec")
    if "rec_yds" in s:
        parts.append(f"{_n(s['rec_yds'])} yds")
    if s.get("rec_td"):
        parts.append(f"{_n(s['rec_td'])} TD")
    if "targets" in s:
        parts.append(f"({_n(s['targets'])} tgt)")
    return " ".join(parts) or None


def _fumbles(s: Stats) -> str | None:
    return f"{_n(s['fumbles_lost'])} fum lost" if s.get("fumbles_lost") else None


def _pair(s: Stats, made: str, att: str, label: str) -> str | None:
    if made not in s and att not in s:
        return None
    if att in s:
        return f"{label} {_n(s.get(made, 0))}/{_n(s[att])}"
    return f"{label} {_n(s[made])}"


def _kicking(s: Stats) -> str | None:
    parts = [p for p in (_pair(s, "fg_made", "fg_att", "FG"), _pair(s, "xp_made", "xp_att", "XP")) if p]
    return " ".join(parts) or None


_DST_COUNTS = (
    ("dst_sacks", "sk"),
    ("dst_int", "int"),
    ("dst_fumble_rec", "fr"),
    ("dst_blocked_kicks", "blk"),
    ("dst_safeties", "saf"),
)
_DST_TDS = (
    "dst_blocked_kick_td",
    "dst_kick_return_td",
    "dst_punt_return_td",
    "dst_fumble_return_td",
    "dst_int_return_td",
)


def _defense(s: Stats) -> str | None:
    if not any(k.startswith("dst_") for k in s):
        return None
    parts = [f"{_n(s[k])} {label}" for k, label in _DST_COUNTS if s.get(k)]
    tds = sum(float(s.get(k, 0)) for k in _DST_TDS)
    if tds:
        parts.append(f"{_n(tds)} TD")
    if "dst_points_allowed" in s:
        parts.append(f"{_n(s['dst_points_allowed'])} pts")
    if "dst_yards_allowed" in s:
        parts.append(f"{_n(s['dst_yards_allowed'])} yds")
    if "dst_points_allowed" in s or "dst_yards_allowed" in s:
        parts.append("allowed")
    return " ".join(parts) or None


def stat_line(stats: Stats | None) -> str:
    """Compact box-score line for one game, e.g. ``19 car 98 yds 2 TD · 3 rec 23 yds (4 tgt)``."""
    s = stats or {}
    segments = (_passing(s), _rushing(s), _receiving(s), _fumbles(s), _kicking(s), _defense(s))
    return " · ".join(seg for seg in segments if seg)
```

- [ ] **Step 4: Verify** — `uv run pytest -q` → `110 passed`

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/cards.py tests/test_cards.py
git commit -m "feat: compact box-score line formatter for player cards"
```

---

### Task 3: `player_card`

**Files:**
- Modify: `src/fantasy_mcp/cards.py`
- Modify: `tests/test_cards.py`

- [ ] **Step 1: Append failing tests to `tests/test_cards.py`** (add these imports at the top: `from fantasy_mcp.cards import player_card, stat_line` replacing the existing import, plus `from fantasy_mcp.shapes import shape_player_card`):

```python
def _nodes(app, node_type):
    def walk(node):
        yield node
        for child in node.get("children") or []:
            yield from walk(child)

    return [n for n in walk(app.to_json()["view"]) if n.get("type") == node_type]


def _profile(player_card_json):
    return shape_player_card(player_card_json["players"][0], player_card_json)


def test_player_card_header_and_metrics(player_card_json):
    app = player_card(_profile(player_card_json))
    assert app.title == "Card Back — RB IND"

    assert [n["content"] for n in _nodes(app, "CardTitle")] == ["Card Back"]
    badges = {n["label"]: n["variant"] for n in _nodes(app, "Badge")}
    assert badges == {"RB · IND": "secondary", "ACTIVE": "success"}
    assert [n["content"] for n in _nodes(app, "CardDescription")] == [
        "Rostered by My Matchup Team · 2025: 362.3 pts"
    ]

    metrics = {n["label"]: n for n in _nodes(app, "Metric")}
    assert metrics["Season pts"]["value"] == 25.1
    assert metrics["Projected"]["value"] == 315.58
    assert metrics["Pos. rank"]["value"] == "#4"
    assert metrics["Owned"]["value"] == "99.9%"
    assert metrics["Owned"]["delta"] == "+0.0%"
    assert metrics["Owned"]["trend"] == "neutral"

    assert [n["content"] for n in _nodes(app, "Muted")] == [
        "Placeholder outlook: workhorse back with elite volume."
    ]


def test_player_card_chart_and_table(player_card_json):
    app = player_card(_profile(player_card_json))

    (chart,) = _nodes(app, "LineChart")
    assert chart["xAxis"] == "week"
    assert chart["data"] == [{"week": "W1", "points": 25.1, "projected": 17.75}]
    assert [s["dataKey"] for s in chart["series"]] == ["points", "projected"]

    (table,) = _nodes(app, "DataTable")
    assert [c["key"] for c in table["columns"]] == ["season", "week", "points", "projected", "line"]
    assert table["paginated"] is True and table["pageSize"] == 10
    assert [(r["season"], r["week"]) for r in table["rows"]] == [(2026, 1), (2025, 18), (2025, 17)]
    assert table["rows"][0]["line"] == "19 car 98 yds 2 TD · 3 rec 23 yds (4 tgt) · 1 fum lost"
    assert table["rows"][0]["projected"] == 17.75
    assert table["rows"][1]["projected"] == "—"


def test_player_card_sparse_profile_does_not_raise():
    profile = {
        "player_id": 1,
        "name": "Rookie",
        "position": "WR",
        "pro_team": "ARI",
        "injury_status": None,
        "injured": None,
        "eligible_slots": [],
        "league_status": "FREEAGENT",
        "owned_by": None,
        "ownership": {"percent_owned": None, "percent_started": None, "percent_change": None, "adp": None},
        "season": {"year": 2026, "projected": None, "points": None, "positional_rank": None},
        "last_season": None,
        "outlook": None,
        "game_log": [],
    }
    app = player_card(profile)
    assert app.title == "Rookie — WR ARI"
    assert [n["label"] for n in _nodes(app, "Badge")] == ["WR · ARI"]
    assert [n["content"] for n in _nodes(app, "CardDescription")] == ["Free agent"]
    assert {n["label"]: n["value"] for n in _nodes(app, "Metric")} == {
        "Season pts": "—",
        "Projected": "—",
        "Pos. rank": "—",
        "Owned": "—",
    }
    assert "delta" not in {n["label"]: n for n in _nodes(app, "Metric")}["Owned"]
    assert _nodes(app, "Muted") == []
    assert _nodes(app, "LineChart") == []
    assert _nodes(app, "DataTable") == []


def test_player_card_status_and_injury_variants(player_card_json):
    profile = _profile(player_card_json)
    profile["league_status"] = "WAIVERS"
    profile["owned_by"] = None
    profile["injury_status"] = "OUT"
    profile["ownership"]["percent_change"] = -1.25
    app = player_card(profile)
    assert [n["content"] for n in _nodes(app, "CardDescription")] == ["On waivers · 2025: 362.3 pts"]
    assert {n["label"]: n["variant"] for n in _nodes(app, "Badge")}["OUT"] == "destructive"
    owned = {n["label"]: n for n in _nodes(app, "Metric")}["Owned"]
    assert owned["delta"] == "-1.2%" or owned["delta"] == "-1.3%"
    assert owned["trend"] == "down" and owned["trendSentiment"] == "negative"

    profile["injury_status"] = "QUESTIONABLE"
    profile["league_status"] = "ONTEAM"
    app = player_card(profile)
    assert {n["label"]: n["variant"] for n in _nodes(app, "Badge")}["QUESTIONABLE"] == "warning"
    assert [n["content"] for n in _nodes(app, "CardDescription")] == ["Rostered · 2025: 362.3 pts"]
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_cards.py -v -k player_card` → `ImportError: cannot import name 'player_card'`

- [ ] **Step 3: Append to `src/fantasy_mcp/cards.py`**

Add these imports below the existing `from typing import Any`:
```python
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Badge,
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    Column,
    DataTable,
    DataTableColumn,
    Metric,
    Muted,
    Row,
    Separator,
)
from prefab_ui.components.charts import ChartSeries, LineChart
```

Append at the end of the file:
```python
_INJURY_VARIANT = {"ACTIVE": "success", "QUESTIONABLE": "warning", "DOUBTFUL": "warning"}
_STATUS_TEXT = {"FREEAGENT": "Free agent", "WAIVERS": "On waivers"}
_DASH = "—"


def _status_line(profile: dict[str, Any]) -> str:
    status = profile.get("league_status")
    if status == "ONTEAM":
        owner = (profile.get("owned_by") or {}).get("name")
        text = f"Rostered by {owner}" if owner else "Rostered"
    else:
        text = _STATUS_TEXT.get(status, str(status))
    last = profile.get("last_season") or {}
    if last.get("points") is not None:
        text += f" · {last.get('year')}: {last['points']} pts"
    return text


def _or_dash(value: Any) -> Any:
    return _DASH if value is None else value


def _owned_metric(ownership: dict[str, Any]) -> Metric:
    owned = ownership.get("percent_owned")
    change = ownership.get("percent_change")
    if owned is None:
        return Metric(label="Owned", value=_DASH)
    if change is None:
        return Metric(label="Owned", value=f"{owned}%")
    trend = "up" if change > 0 else "down" if change < 0 else "neutral"
    sentiment = {"up": "positive", "down": "negative", "neutral": "neutral"}[trend]
    return Metric(
        label="Owned",
        value=f"{owned}%",
        delta=f"{change:+.1f}%",
        trend=trend,
        trend_sentiment=sentiment,
    )


def _chart_rows(profile: dict[str, Any]) -> list[dict[str, Any]]:
    year = (profile.get("season") or {}).get("year")
    rows = [g for g in profile.get("game_log") or [] if g.get("season") == year]
    rows.sort(key=lambda g: g.get("week") or 0)
    return [{"week": f"W{g.get('week')}", "points": g.get("points"), "projected": g.get("projected")} for g in rows]


def _table_rows(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "season": g.get("season"),
            "week": g.get("week"),
            "points": _or_dash(g.get("points")),
            "projected": _or_dash(g.get("projected")),
            "line": stat_line(g.get("stats")),
        }
        for g in profile.get("game_log") or []
    ]


def player_card(profile: dict[str, Any]) -> PrefabApp:
    """Build the Prefab card for a ``get_player`` profile. Never raises on sparse input."""
    name = profile.get("name") or "Unknown player"
    position, team = profile.get("position"), profile.get("pro_team")
    season = profile.get("season") or {}
    ownership = profile.get("ownership") or {}
    injury = profile.get("injury_status")
    rank = season.get("positional_rank")
    chart_rows = _chart_rows(profile)
    table_rows = _table_rows(profile)

    with PrefabApp(title=f"{name} — {position} {team}") as app:
        with Card():
            with CardHeader():
                with Row(gap=2):
                    CardTitle(content=name)
                    Badge(label=f"{position} · {team}", variant="secondary")
                    if injury:
                        Badge(label=str(injury), variant=_INJURY_VARIANT.get(injury, "destructive"))
                CardDescription(content=_status_line(profile))
            with CardContent():
                with Column(gap=4):
                    with Row(gap=4):
                        Metric(label="Season pts", value=_or_dash(season.get("points")))
                        Metric(label="Projected", value=_or_dash(season.get("projected")), description="season")
                        Metric(label="Pos. rank", value=f"#{rank}" if rank is not None else _DASH)
                        _owned_metric(ownership)
                    if profile.get("outlook"):
                        Muted(content=profile["outlook"])
                    if chart_rows or table_rows:
                        Separator()
                    if chart_rows:
                        LineChart(
                            data=chart_rows,
                            series=[
                                ChartSeries(data_key="points", label="Points"),
                                ChartSeries(data_key="projected", label="Projected"),
                            ],
                            x_axis="week",
                            height=160,
                            show_dots=True,
                        )
                    if table_rows:
                        DataTable(
                            columns=[
                                DataTableColumn(key="season", header="Season", sortable=True),
                                DataTableColumn(key="week", header="Wk", sortable=True, align="right"),
                                DataTableColumn(key="points", header="Pts", sortable=True, align="right"),
                                DataTableColumn(key="projected", header="Proj", align="right"),
                                DataTableColumn(key="line", header="Line"),
                            ],
                            rows=table_rows,
                            search=False,
                            paginated=True,
                            page_size=10,
                        )
    return app
```

- [ ] **Step 4: Verify** — `uv run pytest -q` → `114 passed`

Troubleshooting: if a component rejects a kwarg, inspect it with `uv run python -c "from prefab_ui.components import X; print(list(X.model_fields))"` and report the exact field names rather than guessing. If the `Row` inside `CardHeader` isn't allowed, put the badges in a `Row` directly under `Card` instead and say so.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/cards.py tests/test_cards.py
git commit -m "feat: build a Prefab player card from the get_player profile"
```

---

### Task 4: `get_player` becomes an app tool

**Files:**
- Modify: `src/fantasy_mcp/server.py`
- Modify: `tests/test_server.py`
- Modify: `README.md`

- [ ] **Step 1: Update the tests in `tests/test_server.py`**

Replace the three `result.data[...]` assertions in `test_get_player_by_name` with:
```python
    profile = json.loads(result.content[0].text)
    assert profile["player_id"] == 4242335
    assert profile["name"] == "Card Back"
    assert profile["owned_by"]["team_id"] == 12
    assert result.structured_content["$prefab"]["version"]
    assert result.structured_content["view"]["type"] == "Div"
```
Replace `assert result.data["player_id"] == 4242335` in `test_get_player_by_id_skips_index` with:
```python
    assert json.loads(result.content[0].text)["player_id"] == 4242335
```
Append a new test:
```python
async def test_get_player_is_registered_as_an_app(client):
    async with Client(server.mcp) as c:
        tool = next(t for t in await c.list_tools() if t.name == "get_player")
        assert tool.meta["ui"]["resourceUri"].startswith("ui://prefab/")
        others = [t for t in await c.list_tools() if t.name != "get_player"]
        assert all("ui" not in (t.meta or {}) for t in others)
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_server.py -v -k get_player` → the by-name/by-id tests fail (`content[0].text` is the JSON already, but `structured_content` has no `$prefab`), and the registration test fails (no `ui` meta).

- [ ] **Step 3: Implement in `src/fantasy_mcp/server.py`**

Add imports:
```python
import json

from fastmcp.tools import ToolResult

from fantasy_mcp.cards import player_card
```
Change the decorator and return of `get_player`:
```python
@mcp.tool(app=True)
def get_player(name: str | None = None, player_id: int | None = None) -> ToolResult:
```
and replace `return shape_player_card(entries[0], league)` with:
```python
        profile = shape_player_card(entries[0], league)
        return ToolResult(content=json.dumps(profile), structured_content=player_card(profile))
```
Append to the docstring's last paragraph: `In clients that support MCP Apps this renders as a card; the JSON profile is always returned as text.`

- [ ] **Step 4: Verify** — `uv run pytest -q` → `115 passed`. Stdio sanity: `uv run fantasy-mcp </dev/null 2>&1 | grep -E "Traceback|Error" || echo "entrypoint OK"` → `entrypoint OK`.

- [ ] **Step 5: `README.md`** — after the `get_player` bullet add:
```markdown
  In clients that support MCP Apps (Claude Desktop, claude.ai) this renders
  as an interactive card; elsewhere the JSON profile is returned as text.
```

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_mcp/server.py tests/test_server.py README.md
git commit -m "feat: render get_player as a Prefab card"
```

---

### Task 5: Live check

Run by the controller.

- [ ] **Step 1: In-memory render check** — call `get_player(name="Jonathan Taylor")` via `fastmcp.Client`, confirm `content[0].text` is the profile JSON and `structured_content["view"]` contains `CardTitle`, 4 `Metric`s, a `LineChart`, and a `DataTable` with ≥ 17 rows.
- [ ] **Step 2: Real client** — restart `claude` here and ask "tell me about Jonathan Taylor" (JSON path). Then, if Claude Desktop or claude.ai is configured with this server, ask the same there and confirm the card renders (`uv run --directory /path/to/fantasy-mcp fantasy-mcp` in that client's MCP config).
