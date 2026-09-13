# `get_free_agents` Tool — Design

**Date:** 2026-09-13
**Status:** Approved
**Builds on:** `2026-09-13-espn-mcp-basic-design.md`, `2026-09-13-matchup-tool-design.md`

## Goal

Add `get_free_agents(position, limit, sort)` returning available players
(free agents and waiver claims) with ownership, projection, and rank data so
Claude can answer "who should I pick up?".

## Scope

In:
- `get_free_agents` tool with optional `position`, `limit`, `sort`
- New `filters.py` module that builds ESPN `X-Fantasy-Filter` payloads
- `shapes.shape_free_agent`; generalize the matchup stat lookup so both
  matchup and free-agent shaping share one helper

Out (later): next-week per-player projections (not returned by this view
by default), player news/outlook text, add/drop actions, trending queries
beyond the `percent_change` field, opponent/matchup ratings.

## ESPN facts (verified live 2026-09-13)

- View `kona_player_info` on the league endpoint with header
  `X-Fantasy-Filter: {"players": {...}}` returns `{"players": [...],
  "positionAgainstOpponent": {...}}` and nothing else — no top-level
  `scoringPeriodId`. Adding the `mStatus` view (`?view=kona_player_info&
  view=mStatus`) keeps `players` and adds `scoringPeriodId`, `status`, etc.
  Ignore `positionAgainstOpponent`.
- Filter keys that work:
  - `filterStatus: {"value": ["FREEAGENT", "WAIVERS"]}`
  - `filterSlotIds: {"value": [<lineupSlotId>]}` — QB 0, RB 2, WR 4, TE 6,
    K 17, D/ST 16
  - `limit: N`
  - `sortPercOwned: {"sortPriority": 1, "sortAsc": false}`
  - `sortAppliedStatTotal: {"sortPriority": 1, "sortAsc": false, "value":
    "10<season>"}` sorts by season projected total (`"102026"` for 2026)
- Each `players[]` entry: `status` (`FREEAGENT`|`WAIVERS`), `onTeamId` (0),
  `ratings: {"0": {"positionalRanking", "totalRanking", "totalRating"}}`,
  `player: {fullName, defaultPositionId, proTeamId, injuryStatus,
  eligibleSlots, ownership: {percentOwned, percentChange, percentStarted,
  averageDraftPosition}, stats: [...]}`.
- `player.stats[]` items: `scoringPeriodId` (0 = season total, N = week N),
  `statSourceId` (0 = actual, 1 = projected), `appliedTotal`. Only the
  current week's and the season's entries are present by default.

## Layout changes

```
src/fantasy_mcp/
├── filters.py   # NEW: X-Fantasy-Filter builders (request side)
├── shapes.py    # + shape_free_agent, generalized _stat helper
├── server.py    # + get_free_agents tool
tests/
├── test_filters.py                 # NEW
├── test_shapes.py                  # + free-agent shaping tests
├── test_server.py                  # + tool tests
└── fixtures/free_agents.json       # NEW: trimmed real kona_player_info
```

## `filters.py`

```python
POSITION_SLOTS: dict[str, int] = {
    "QB": 0, "RB": 2, "WR": 4, "TE": 6, "K": 17, "D_ST": 16,
}
SORTS = ("owned", "projected")
MAX_LIMIT = 50


def free_agent_filter(
    *, season: int, position: str | None, limit: int, sort: str
) -> dict[str, Any]:
```

Behavior:
- `position` is upper-cased and looked up in `POSITION_SLOTS`; unknown →
  `ValueError` listing valid values. `None` → no `filterSlotIds`.
- `limit` outside `1..MAX_LIMIT` → `ValueError`.
- `sort` not in `SORTS` → `ValueError`.
- Returns
  ```python
  {"players": {
      "filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
      "filterSlotIds": {"value": [slot]},            # only if position
      "limit": limit,
      # one of:
      "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
      "sortAppliedStatTotal": {"sortPriority": 1, "sortAsc": False,
                               "value": f"10{season}"},
  }}
  ```

`filters.py` imports nothing from the rest of the package (pure).

## `shapes.py`

Generalize the existing projection lookup:

```python
def _stat(player: dict, *, period: int, source: int) -> float | None:
    """appliedTotal (rounded 2) of the stats[] item with the given
    scoringPeriodId and statSourceId, else None."""
```

`_projected_points(player, scoring_period)` becomes
`_stat(player, period=scoring_period, source=PROJECTION_SOURCE_ID)`. Add
`ACTUAL_SOURCE_ID = 0` and `SEASON_PERIOD = 0` constants beside
`PROJECTION_SOURCE_ID`. Matchup behavior and tests unchanged.

New:

```python
def shape_free_agent(entry: dict, scoring_period: int) -> dict:
```

Returns:

| key                | source                                                       |
|--------------------|--------------------------------------------------------------|
| `name`             | `player.fullName`                                            |
| `position`         | `ids.name(POSITIONS, player.defaultPositionId)`              |
| `pro_team`         | `ids.name(PRO_TEAMS, player.proTeamId)`                      |
| `injury_status`    | `player.injuryStatus`                                        |
| `status`           | `entry.status` (`FREEAGENT` / `WAIVERS`)                     |
| `percent_owned`    | `player.ownership.percentOwned` rounded 1; null if absent    |
| `percent_change`   | `player.ownership.percentChange` rounded 2; null if absent   |
| `season_projected` | `_stat(period=0, source=1)`                                  |
| `season_points`    | `_stat(period=0, source=0)`                                  |
| `week_projected`   | `_stat(period=scoring_period, source=1)`                     |
| `week_points`      | `_stat(period=scoring_period, source=0)`                     |
| `positional_rank`  | `entry.ratings["0"].positionalRanking`; null if absent       |

All lookups use `.get`; a missing `player`, `ownership`, `stats`, or
`ratings` yields nulls (and `UNKNOWN_-1` names), never an exception.

## `server.py`

```python
@mcp.tool
def get_free_agents(
    position: str | None = None,
    limit: int = 10,
    sort: str = "owned",
) -> dict[str, Any]:
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
    except ValueError as e:
        raise ToolError(str(e)) from e
    except (EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e
```

Docstring: when to use ("who should I pick up", "best available RB",
"who's trending"); parameter values (position list incl. `D_ST`, limit
1–50 default 10, sort `owned` = most rostered first / `projected` = highest
season projection first); field meanings (`status` WAIVERS means a claim is
needed, `percent_change` is ownership trend, `week_*` are current NFL week,
`season_*` are season-to-date/projected totals); caveat that next-week
projections are not available.

`INSTRUCTIONS`: add "Use get_free_agents for pickup/waiver questions" and
list four tools; keep "no standings, transaction, or past-week data".

## Errors

Argument errors (`ValueError` from `filters.py`) and ESPN errors both
surface as `ToolError` with the original message. Argument messages must
name the valid values, e.g. `position must be one of QB, RB, WR, TE, K,
D_ST (got 'FLEX')`.

## Testing

`tests/fixtures/free_agents.json`: real `kona_player_info` response trimmed
to `{"scoringPeriodId": 1, "players": [two entries]}` — one `WAIVERS` RB
with full `ownership`, `ratings`, and four `stats` (week actual/proj,
season actual/proj), one `FREEAGENT` WR with no `stats`, no `ratings`, no
`ownership`. Names replaced with placeholders.

`tests/test_filters.py`:
- default (no position, limit 10, owned) → exact dict, no `filterSlotIds`
- position "rb" (lower-case) → `filterSlotIds [2]`
- `D_ST` → 16
- sort "projected" → `sortAppliedStatTotal` with value `"102026"` and no
  `sortPercOwned`
- invalid position / sort / limit 0 / limit 51 → `ValueError` whose message
  contains the valid values

`tests/test_shapes.py`:
- `shape_free_agent` exact dict for the full entry
- sparse entry → nulls, `UNKNOWN_-1`, no exception
- existing matchup tests unchanged after the `_stat` refactor

`tests/test_server.py`:
- `get_free_agents({"position": "RB", "limit": 5, "sort": "projected"})`
  via in-memory client: response shape; request `view == ["kona_player_info",
  "mStatus"]`;
  `X-Fantasy-Filter` header parses to the expected filter dict
- invalid position → `ToolError` matching "position must be one of"
- default args → header has `sortPercOwned`, no `filterSlotIds`

Manual: live `get_free_agents(position="RB")` and `sort="projected"`
against the user's league.
