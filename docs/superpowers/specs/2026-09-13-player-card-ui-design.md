# Player Card UI (Prefab) — Design

**Date:** 2026-09-13
**Status:** Approved
**Builds on:** `2026-09-13-player-card-tool-design.md`

## Goal

Render `get_player` as an interactive card in MCP-Apps-capable clients
(Claude Desktop, claude.ai) using FastMCP Prefab, while Claude keeps
receiving the exact same JSON profile it gets today.

## Scope

In:
- `get_player` becomes an app tool (`@mcp.tool(app=True)`) returning
  `ToolResult(content=<profile JSON text>, structured_content=<PrefabApp>)`
- New pure module `cards.py`: `player_card(profile) -> PrefabApp` and a
  compact box-score line formatter
- Dependency: `fastmcp[apps]`, `prefab-ui` pinned to `0.20.2`

Out (later): cards/grids for `get_my_team`, `get_matchup`,
`get_free_agents`; interactive state (tabs, filters); custom theme;
images/headshots.

## Verified facts (2026-09-13, fastmcp 4.0.3, prefab-ui 0.20.2)

- `@mcp.tool(app=True)` adds `_meta.ui.resourceUri = "ui://prefab/tool/<hash>/renderer.html"`
  to the tool and registers that resource.
- Returning `ToolResult(content=json_text, structured_content=app)`
  yields `content = [TextContent(json_text)]` and
  `structuredContent = {"$prefab": {"version": "0.3"}, "view": {...}}`.
  Consequently `fastmcp.Client(...).call_tool(...).data` is the view, not
  the profile — the profile is `json.loads(result.content[0].text)`.
- Components used: `prefab_ui.app.PrefabApp(title=...)` as a context
  manager; `prefab_ui.components`: `Card, CardHeader, CardTitle,
  CardDescription, CardContent, Row, Column, Badge(label, variant),
  Metric(label, value, description, delta, trend, trend_sentiment),
  Muted(content), Separator, DataTable(columns, rows, search, paginated,
  page_size), DataTableColumn(key, header, sortable, align)`;
  `prefab_ui.components.charts`: `LineChart(data, series, x_axis, height,
  show_dots, show_legend, show_tooltip)`, `ChartSeries(data_key, label)`.
- `Badge.variant` ∈ default, secondary, destructive, success, warning, info,
  outline, ghost.
- `Metric.trend` ∈ up/down/neutral; `trend_sentiment` ∈ positive/negative/neutral.
- Clients without MCP Apps support (e.g. the Claude Code terminal) show the
  text content only — identical to today's behavior.

## Layout changes

```
src/fantasy_mcp/
├── cards.py     # NEW: player_card(profile) -> PrefabApp; stat_line(stats) -> str
├── server.py    # get_player -> app tool returning ToolResult
pyproject.toml   # fastmcp[apps], prefab-ui==0.20.2
tests/
├── test_cards.py          # NEW
└── test_server.py         # get_player tests read content[0].text
```

## `cards.py` (pure; imports `prefab_ui` and `Any` only)

```python
def stat_line(stats: dict[str, int | float]) -> str:
def player_card(profile: dict[str, Any]) -> PrefabApp:
```

### `stat_line`

Compact, position-agnostic box-score string built from the named stats
`shape_stat_line` emits. Segments joined by `" · "`; each segment omits
absent parts; empty when nothing matches.

| segment | built when | format |
|---------|-----------|--------|
| passing | any of pass_comp/pass_att/pass_yds/pass_td/pass_int | `18/34 164 yds 2 TD 1 INT` (INT only if >0; if att missing show `164 yds ...`) |
| rushing | rush_att or rush_yds or rush_td | `19 car 98 yds 2 TD` |
| receiving | receptions or targets or rec_yds or rec_td | `3 rec 23 yds 1 TD (4 tgt)` (tgt only if targets present) |
| fumbles | fumbles_lost | `1 fum lost` |
| kicking | fg_made or fg_att or xp_made or xp_att | `FG 2/2 XP 5/5` (each pair only if either value present; missing att shown as made only, e.g. `FG 2`) |
| defense | any dst_* | `2 sk 1 int 1 fr 23 pts 251 yds allowed` (sk/int/fr/blk/saf only if >0; pts/yds allowed if present) |

Numbers render without trailing `.0`. Ordering: passing, rushing,
receiving, fumbles, kicking, defense.

### `player_card`

Input is the `get_player` profile dict. Output view:

```
PrefabApp(title=f"{name} — {position} {pro_team}")
└ Card
  ├ CardHeader
  │ ├ Row(gap=2): CardTitle(name), Badge(f"{position} · {pro_team}", secondary),
  │ │            Badge(injury_status, <variant below>)          # omitted if injury_status is None
  │ └ CardDescription(<status line>)
  └ CardContent (Column gap=4)
    ├ Row(gap=4):
    │   Metric("Season pts", season.points or "—")
    │   Metric("Projected", season.projected or "—", description="season")
    │   Metric("Pos. rank", f"#{season.positional_rank}" or "—")
    │   Metric("Owned", f"{percent_owned}%" or "—", delta=percent_change,
    │          trend=up/down/neutral by sign, trend_sentiment=positive/negative/neutral)
    ├ Muted(outlook)                                             # omitted if None
    ├ Separator                                                # omitted if neither chart nor table follows
    ├ LineChart(data=<this season's game_log rows ascending by week:
    │             {"week": "W1", "points": 25.1, "projected": 17.75}>,
    │           series=[ChartSeries("points","Points"), ChartSeries("projected","Projected")],
    │           x_axis="week", height=160, show_dots=True)        # omitted with fewer than 2 games this season
    └ DataTable(columns=[Season, Wk, Pts, Proj, Line], rows=<all game_log rows,
                newest first, Line=stat_line(stats), Proj="—" when None>,
                search=False, paginated=True, page_size=10)      # omitted if game_log empty
```

Status line: `ONTEAM` → `Rostered by {owned_by.name}` (or `Rostered` if
owned_by is None); `FREEAGENT` → `Free agent`; `WAIVERS` → `On waivers`;
None → `Status unknown`; anything else → the raw value (a missing name
renders as `Unknown player`). If `last_season` present, append
` · {year}: {points} pts`.

Injury badge variant: `ACTIVE` → `success`; `QUESTIONABLE`/`DOUBTFUL` →
`warning`; anything else non-null (`OUT`, `INJURY_RESERVE`, `SUSPENSION`,
…) → `destructive`.

Metric trend from `percent_change`: `> 0` up/positive, `< 0`
down/negative, else neutral/neutral; `delta` shown as `f"{change:+.1f}%"`;
omitted when percent_change is None.

All values are read with `.get`; the function must never raise on a
sparse profile (nulls everywhere, empty game_log).

## `server.py`

```python
from fastmcp.tools import ToolResult
from fantasy_mcp.cards import player_card

@mcp.tool(app=True)
def get_player(...) -> ToolResult:
    ...
    profile = shape_player_card(entries[0], league)
    text = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))  # byte-identical to the old dict return
    try:  # build and serialize the card; a presentation bug must never cost the data
        return ToolResult(content=text, structured_content=player_card(profile))
    except Exception:
        logger.exception("player_card failed to render; returning JSON only")
        return ToolResult(content=text)
```
Docstring gains one sentence: "In clients that support MCP Apps this
renders as a card; the JSON profile is always returned as text." Error
paths unchanged (`ToolError`).

## Errors

Unchanged for the data path. `player_card` must not raise for any profile
`shape_player_card` can produce (the sparse-profile test is mandatory); as
defense in depth the tool also catches any card build/serialization error,
logs it to stderr, and returns the JSON text alone.

## Testing

`tests/test_cards.py`:
- `stat_line` per position from the live-verified numbers: QB
  `18/34 164 yds 2 TD · 5 car 31 yds`; RB `19 car 98 yds 2 TD · 3 rec 23 yds (4 tgt) · 1 fum lost`;
  WR `10 rec 182 yds (13 tgt)`; K `FG 2/2 XP 5/5`; D/ST
  `2 sk 1 int 1 fr 23 pts 251 yds allowed`; empty `{}` → `""`.
- `player_card` on the fixture-derived profile (call
  `shape_player_card(player_card_json["players"][0], player_card_json)`):
  serialize with `app.model_dump(by_alias=True, exclude_none=True)` and
  assert: title contains "Card Back"; a Badge with label "RB · IND" and one
  with "ACTIVE" variant success; CardDescription "Rostered by My Matchup
  Team · 2025: 362.3 pts"; Metric values 25.1 / 315.58 / "#4" / "99.9%";
  with a second 2026 game added, LineChart data has 2 rows (`W1`, `W2`);
  with the fixture as-is (one game) no LineChart is emitted; DataTable has
  the game rows and the week-1 row's Line is the RB string above.
- Sparse profile (all nulls, empty game_log, `league_status` "FREEAGENT")
  → no exception; description "Free agent"; no LineChart/DataTable/Muted
  nodes present; metrics show "—".
- Injury variants: OUT → destructive; QUESTIONABLE → warning.

`tests/test_server.py` (existing `get_player` tests adjusted):
- `json.loads(result.content[0].text)` equals the profile
  (`player_id == 4242335`, `owned_by.team_id == 12`, …) — replaces
  `result.data[...]` assertions.
- `result.structured_content["$prefab"]` present and
  `["view"]["type"] == "Div"`.
- tool listing: `get_player`'s `meta["ui"]["resourceUri"]` starts with
  `ui://prefab/`.
- Error-path tests unchanged.

Manual: from Claude Desktop or claude.ai with this server configured, ask
"tell me about Jonathan Taylor" and confirm the card renders; from Claude
Code confirm the JSON still arrives.
