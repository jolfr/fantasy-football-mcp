# `get_projections` Tool — Design

**Date:** 2026-09-14
**Status:** Approved

## Goal

Weekly projections for the user's roster with opponent/bye context and a
suggested optimal lineup, so Claude can answer "set my lineup" and
"start X or Y?" with the league's actual slots.

## Verified facts (2026-09-14, live)

- Adding query param `scoringPeriodId=<week>` to the league endpoint makes
  `kona_player_info` return that week's projection (`player.stats[]` item
  with `seasonId == season`, `scoringPeriodId == week`, `statSourceId == 1`).
  Week 2 projections exist while the league's `scoringPeriodId` is still 1.
- `player.eligibleSlots` (list of lineupSlotIds) comes back with
  `kona_player_info`.
- League-independent pro schedules: `GET {BASE}/seasons/{season}?view=proTeamSchedules_wl`
  → `settings.proTeams[]` of `{id, abbrev, byeWeek, proGamesByScoringPeriod:
  {"<week>": [{homeProTeamId, awayProTeamId, date (epoch ms), scoringPeriodId}]}}`.
  33 entries (id 0 = free agents).
- `positionAgainstOpponent` ratings are empty this early in the season —
  out of scope.
- `rosterSettings.lineupSlotCounts` gives starting slot counts (BENCH 20 and
  IR 21 are not starting slots). Flex-type slots: 23 FLEX (RB/WR/TE),
  3 RB/WR, 5 WR/TE, 7 OP (QB/RB/WR/TE), 25 RB/WR/TE. Dedicated slots:
  0 QB, 2 RB, 4 WR, 6 TE, 16 D/ST, 17 K.

## Changes

### `espn.py`
- `get(*views, fantasy_filter=None, scoring_period: int | None = None)` —
  appends `("scoringPeriodId", str(scoring_period))` to the params when given.
- `get_pro_schedules() -> dict` — GET `{BASE}/seasons/{season}` with
  `view=proTeamSchedules_wl`; validates a dict body; `not_found` hint names
  `ESPN_SEASON`.

### `filters.py`
- `player_ids_filter(player_ids: list[int]) -> dict` →
  `{"players": {"filterIds": {"value": [...]}}}` (fresh dict).

### `schedules.py` (new, pure)
```python
def game_context(schedules: dict, pro_team_id: int | None, week: int) -> dict:
    # -> {"opponent": "@KC" | "vs BUF" | "BYE" | None, "kickoff": "2026-09-20T17:00:00Z" | None}
```
Builds `{id: team}` from `settings.proTeams`. BYE when `byeWeek == week` or
no game that week; `@` when the team is `awayProTeamId`, `vs` when home;
opponent abbrev from the other team's `abbrev` upper-cased; `kickoff` = ISO
UTC from `date`. `None`/`None` when the team id is unknown.

### `lineup.py` (new, pure)
```python
DEDICATED_SLOTS = (0, 2, 4, 6, 16, 17)
NON_STARTING_SLOTS = {20, 21}

def optimal_lineup(players: list[dict], slot_counts: dict[int, int]) -> dict[int, list[dict]]:
```
`players` rows carry `player_id`, `projected` (float or None → 0),
`eligible_slots` (list[int]), `slot_id` (current). Excludes players
currently in IR (21). Fills each dedicated slot in `DEDICATED_SLOTS` order
with the top-`count` unassigned players whose `eligible_slots` include it
(sort key: projected desc, currently-in-that-slot first, then player_id);
then every remaining starting slot (flex-type) in ascending slot-id order
the same way. Returns `{slot_id: [rows]}` for starting slots only.
Greedy is optimal because dedicated slots are disjoint and flex takes the
remainder.

### `shapes.py`
```python
def shape_projections(week, roster_entries, projections_players, schedules, slot_counts) -> dict
```
- Row per roster entry: `player_id, name, position, pro_team, injury_status,
  slot` (current, `ids.LINEUP_SLOTS`), `opponent, kickoff` (from
  `game_context`), `projected` (from the projections payload by id; `None` if
  ESPN has none; rounded 2). Sorted: current starters by slot id, then bench/
  IR by projected desc.
- `current_total` = sum of projected over current starters (None → 0).
- `suggested_lineup` = `optimal_lineup(...)` flattened to rows
  `{slot, player_id, name, projected}` in slot-id order; `suggested_total`.
- `changes`: `{"start": [rows newly starting], "sit": [rows no longer
  starting]}` comparing player-id sets; `gain = round(suggested_total -
  current_total, 2)`.
- Never raises on missing data: unknown ids → `projected None`, empty
  schedules → opponent/kickoff None.

Output:
```json
{"week": 2, "players": [...], "current_total": 91.5,
 "suggested_lineup": [{"slot": "QB", "player_id": ..., "name": ..., "projected": 19.4}, ...],
 "suggested_total": 101.5,
 "changes": {"start": [...], "sit": [...], "gain": 10.0}}
```

### `server.py`
```python
@mcp.tool
def get_projections(week: int | None = None) -> dict[str, Any]:
```
1. `league = client.get("mRoster", "mSettings")`; `team_id = client.find_my_team_id(league)`;
   `entries = team_by_id(...)["roster"]["entries"]`; `slot_counts` from
   `settings.rosterSettings.lineupSlotCounts` (int keys).
2. `week = week or league["scoringPeriodId"]`; validate `1 <= week <= 18` else
   `ToolError`.
3. `proj = client.get("kona_player_info", fantasy_filter=player_ids_filter(ids), scoring_period=week)`.
4. `schedules = _get_pro_schedules(client)` — module cache like the player
   index (`set_pro_schedules_for_tests`).
5. `return shape_projections(week, entries, proj["players"], schedules, slot_counts)`.
Errors → `ToolError` as usual. Docstring: when to use, `week` semantics
("current NFL week by default; pass next week's number once this week's
games have started"), field meanings, that `suggested_lineup` respects the
league's slots and eligibility, that IR players are never moved, that
projections are ESPN's. INSTRUCTIONS: "For start/sit or 'set my lineup'
call get_projections (next week's number if this week's games have started)
and present changes; get_projections already applies league slots, so
get_league_settings is not needed for that."

## Testing

Fixtures (trimmed real, scrubbed, already on disk):
- `tests/fixtures/roster_settings.json`: my team (id 12) with 8 entries —
  QB One (slot 0), RB One (2), WR One (4), WR Two (4), TE One (6), Def One
  (16), Kicker One (17), WR Bench (20); FLEX (23) empty; real
  `lineupSlotCounts`.
- `tests/fixtures/projections.json`: week-2 projections for those 8 ids
  (WR Bench 10.02, WR One 15.25, WR Two 14.73, RB One 17.68, QB One 19.4,
  TE One 9.96, Def One 6.82, Kicker One 8.92) with `eligibleSlots`.
- `tests/fixtures/pro_schedules.json`: 20 pro teams, weeks 1–3, real byes
  (IND 13, KC 5, BAL 13, ...); IND week 2 is `@KC`.

Tests: `game_context` home/away/bye/unknown; `optimal_lineup` fills FLEX
with WR Bench, respects counts, skips IR, tie-breaks keep the current
starter; `shape_projections` exact rows for the fixture (`RB One` →
opponent `@KC`, kickoff ISO), totals (`current_total` = sum of 7 starters,
`suggested_total` = + 10.02), `changes.start == [WR Bench@FLEX]`,
`changes.sit == []`, `gain == 10.02`; a bye test (set a team's `byeWeek` to
2 → `opponent "BYE"`, still eligible but projected 0/None); client tests for
`scoring_period` param and `get_pro_schedules`; tool test asserts the three
requests (views + `scoringPeriodId=2` + filter ids), default week from
`scoringPeriodId`, invalid week → `ToolError`; registration lists seven
tools.

Live: `get_projections(week=2)` shows next week's opponents and a sane
suggested lineup for the user's roster.
