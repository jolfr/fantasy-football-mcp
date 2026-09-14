# `get_team` Tool — Design

**Date:** 2026-09-14
**Status:** Approved

## Goal

Any league team's roster (trade targets, positional depth), by team id or
name/abbreviation, with the current week's projection per player.

## Verified facts

- `mRoster` returns `teams[]` with `roster.entries[]` for every team;
  entries carry `playerId`, `lineupSlotId`, `playerPoolEntry.player` incl.
  `stats[]` for the current scoring period (used by `get_matchup` for
  projections). `mTeam` adds `name/abbrev/owners/record`; `members[]` gives
  owner names (see standings design).

## Changes

`shapes.py`:
- `find_team_by_name(league, query) -> dict` — `query` matched
  case-insensitively against `abbrev` (exact), then `name` (exact), then
  `name` contains; exactly one hit → team; none → `EspnError("No team
  matches 'x'. Teams: NAME (ABBR, id N); ...")`; several → `EspnError`
  listing the candidates the same way.
- `shape_team(team, *, league=None, scoring_period=None, season=None)` —
  unchanged output when the keyword args are omitted; when `league` is
  given, adds `"owner": _owner_name(league, team)` and each roster row
  gains `"projected"` (current-period player projection via `_stat`, null
  if absent). `get_my_team` starts passing these too so both tools share
  one row shape.

`server.py`:
```python
@mcp.tool
def get_team(team: str | int) -> dict[str, Any]:
```
- `league = client.get("mTeam", "mRoster")`; int (or digit string) →
  `team_by_id`, else `find_team_by_name`; return
  `shape_team(found, league=league, scoring_period=league["scoringPeriodId"],
  season=league["seasonId"])`.
- Docstring: when to use; `team` accepts id (from get_standings/get_matchup)
  or name/abbrev; `is_me` not included (use get_my_team); projected =
  current NFL week. INSTRUCTIONS: "Use get_team for another manager's
  roster (trade targets, positional depth); get_standings lists team ids."
  Ten tools.

## Testing

Fixture: extend `mteam_mroster.json` with `members` (placeholder names) and
`scoringPeriodId`/`seasonId`; add one `stats[]` projection to Josh Allen's
entry. Tests: `find_team_by_name` abbrev/name/contains/none/ambiguous;
`shape_team` with league adds `owner` and `projected`; tool by id, by
"MYS", by "rival" (contains), unknown → ToolError listing teams; ten tools.
