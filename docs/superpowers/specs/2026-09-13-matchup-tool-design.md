# `get_matchup` Tool — Design

**Date:** 2026-09-13
**Status:** Approved
**Builds on:** `2026-09-13-espn-mcp-basic-design.md` (v0.1)

## Goal

Add one tool, `get_matchup`, returning the user's current-week head-to-head
matchup: both teams' live score, projection, win probability, and every
rostered player (starters and bench) with actual and projected points.

## Scope

In:
- `get_matchup()` — no parameters; current matchup period only
- Move existing payload-shaping helpers out of `server.py` into a new
  `shapes.py` so `server.py` contains only MCP plumbing and tools

Out (later): past weeks (`scoringPeriodId` param), full league scoreboard,
playoff bracket, per-stat breakdowns.

## ESPN facts (verified live 2026-09-13)

- Views: `mMatchup` + `mMatchupScore` give `schedule[]`; `mTeam` gives team
  names. All three in one `get()` call.
- `status.currentMatchupPeriod` = current week; `scoringPeriodId` at top
  level = current NFL week (equal in this league; `matchupPeriodLength` is 1).
- Each `schedule[]` game: `id`, `matchupPeriodId`, `winner`
  (`UNDECIDED`/`HOME`/`AWAY`/`TIE`), `home`, `away`.
- Each side: `teamId`, `totalPoints`, `totalPointsLive`,
  `totalProjectedPoints`, `totalProjectedPointsLive`, `winProbability`,
  `rosterForCurrentScoringPeriod.entries[]` (full roster, all slots, only
  for the current period).
- Each entry: `lineupSlotId`, `playerPoolEntry.appliedStatTotal` (actual
  points so far), `playerPoolEntry.player.{fullName, defaultPositionId,
  proTeamId, injuryStatus, stats[]}`; in `stats[]`, the item with
  `statSourceId == 1` and matching `scoringPeriodId` is the projection
  (`appliedTotal`), `statSourceId == 0` is actual.
- `rosterForMatchupPeriod` is NOT useful (slot ids zeroed, partial) — ignore.

## Layout changes

```
src/fantasy_mcp/
├── server.py   # FastMCP app + tools only (whoami, get_my_team, get_matchup)
├── shapes.py   # NEW: pure dict -> dict shaping (moved + new functions)
├── espn.py     # unchanged
├── config.py   # unchanged
└── ids.py      # unchanged
tests/
├── test_shapes.py          # NEW: moved shaping tests + matchup shaping tests
├── test_server.py          # tool tests only
└── fixtures/matchup.json   # NEW: trimmed real mMatchup+mMatchupScore+mTeam
```

## `shapes.py`

Moved from `server.py` (behavior unchanged; `team_by_id` now shares a private
`_find_team` lookup with `_shape_side`):
`team_by_id`, `shape_whoami`, `shape_team`, `_shape_player`, `_slot_sort_key`.

New:

```python
def find_matchup(league: dict, team_id: int, period: int) -> dict:
    """Return the schedule[] game in `period` where home or away teamId == team_id.
    Raises EspnError(f"No matchup for your team in week {period}") if none (bye)."""

def shape_matchup(game: dict, league: dict, my_team_id: int) -> dict:
```

`shape_matchup` output:

```json
{
  "week": 1,
  "status": "IN_PROGRESS",
  "is_home": true,
  "my_team":  { "team_id": 12, "name": "...", "abbrev": "...",
                "score": 59.2, "projected": 128.52, "win_probability": 0.67,
                "roster": [ <row>, ... ] },
  "opponent": { same shape }
}
```

Row = `_shape_player(entry)` fields (`name`, `position`, `slot`, `pro_team`,
`injury_status`) plus:
- `points`: `playerPoolEntry.appliedStatTotal` rounded 2 (absent/null → `0.0`)
- `projected`: `appliedTotal` of the `player.stats[]` item with
  `statSourceId == 1` and `scoringPeriodId == league["scoringPeriodId"]`,
  rounded 2; `null` if none

Rows ordered by `_slot_sort_key` (starters, then BENCH, then IR).

Side fields:
- `score`: `totalPointsLive` if not null else `totalPoints`; null → `0.0`; rounded 2
- `projected`: `totalProjectedPointsLive` if not null else
  `totalProjectedPoints`; `null` if neither; rounded 2
- `win_probability`: `winProbability` or `null`
- `name`/`abbrev`: from `team_by_id`-style lookup in `league["teams"]`;
  `null` if the team id is missing (do not raise)
- `roster`: from `rosterForCurrentScoringPeriod.entries`; `[]` if missing

`week` = `game["matchupPeriodId"]`.

`status`:
- `winner in ("HOME", "AWAY", "TIE")` → `"FINAL"`
- `winner == "UNDECIDED"` and either side's `score > 0` → `"IN_PROGRESS"`
- otherwise → `"UPCOMING"`

`is_home` = `game["home"]["teamId"] == my_team_id`.

## `server.py`

```python
@mcp.tool
def get_matchup() -> dict[str, Any]:
    """Return the user's current-week head-to-head matchup. ..."""
    try:
        client = _get_client()
        league = client.get("mMatchup", "mMatchupScore", "mTeam")
        team_id = client.find_my_team_id(league)
        week = league.get("status", {}).get("currentMatchupPeriod")
        if week is None:
            raise EspnError("ESPN response is missing status.currentMatchupPeriod.")
        game = find_matchup(league, team_id, week)
        return shape_matchup(game, league, team_id)
    except (EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e
```

Docstring explains: when to use (score/projection/opponent/per-player points;
it cannot tell who has played yet),
field meanings (`score` is live points so far; `projected` is ESPN's live
projection; `status` values; `slot` BENCH/IR = not counting), and that it
covers the current week only.

Existing tools unchanged except imports now come from `shapes`.

## Errors

Same convention as v0.1: everything surfaces as `EspnError` → `ToolError`.
New message: `"No matchup for your team in week {N} (bye week?)"`.

## Testing

`tests/fixtures/matchup.json`: real response, trimmed to the two teams in
the user's week-1 game, 3–4 roster entries per side (one starter with a
projection, one without `stats`, one BENCH, one IR), `status`,
`scoringPeriodId`, `settings.name`. Owner SWIDs and member data scrubbed;
team/player names replaced with placeholders. My team id 12, opponent 11,
`matchupPeriodId` 1; plus a second schedule entry for period 2 between two
other teams so the bye-week path can be exercised.

`tests/test_shapes.py`:
- moved tests (`shape_team` ordering/ids, tolerates entry without player,
  `shape_whoami`, `team_by_id` missing) — unchanged assertions
- `find_matchup` returns the period-1 game for team 12; raises `EspnError`
  matching "week 2" for team 12 in period 2
- `shape_matchup`: full exact dict for the fixture (week, status
  IN_PROGRESS, is_home, both sides' score/projected/win_probability,
  roster row order and values incl. `projected: None` for the
  no-stats player)
- status derivation: `winner: "HOME"` → FINAL; UNDECIDED with zero live
  scores → UPCOMING
- `score` falls back to `totalPoints` when `totalPointsLive` absent
- opponent missing from `teams[]` → `name`/`abbrev` None, no raise

`tests/test_server.py`:
- `get_matchup` tool via in-memory client returns `my_team.team_id == 12`
  and asserts the request's `view` list is `["mMatchup", "mMatchupScore",
  "mTeam"]`
- existing tool tests unchanged

Manual: live `get_matchup` against the user's league before merge.

## Addendum 2026-09-14: `week` parameter

**Verified live:** `?scoringPeriodId=<week>` on the league endpoint returns
the `schedule[]` game for that matchup period with
`rosterForCurrentScoringPeriod` populated for that week (past weeks:
final `totalPoints`, `winner` set; future weeks: projections only,
`totalPointsLive` absent → status `UPCOMING`). The response's top-level
`scoringPeriodId` echoes the requested week, which `shape_matchup` already
uses to select per-player projections.

`get_matchup(week: int | None = None)`: `week` validated 1–18 (as in
`get_projections`); when given, the request adds `scoring_period=week` and
`find_matchup` uses `week`; when omitted, behavior is unchanged (current
matchup period from `status`). Output gains `current_week`
(`status.currentMatchupPeriod`). Docstring/INSTRUCTIONS: "pass `week` for
a past result or next week's preview". The "no past-week matchup data"
caveat is removed.
