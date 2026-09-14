# `compare_players` Tool — Design

**Date:** 2026-09-14
**Status:** Approved

## Goal

Side-by-side comparison of 2–6 players (by name or id) for "X or Y?"
decisions: this week's projection and opponent, season pace, recent form,
last season, availability in the league, and ownership trend — in one call.

## Verified facts (2026-09-14, live)

- `kona_playercard` + `mTeam` + `mStatus` with `filterIds` of several ids
  returns all of them in one response, in ESPN's order (not the request
  order).
- The player-card stat filter does NOT include future-week projections even
  when published; adding `scoringPeriodId=<week>` as a query param
  (`EspnClient.get(scoring_period=week)`) adds that week's projection
  (`seasonId == season, scoringPeriodId == week, statSourceId == 1`) while
  keeping the full game log. The response's top-level `scoringPeriodId`
  then echoes the requested week; the league's current week is
  `status.currentMatchupPeriod`.

## Changes

`filters.py`: `player_card_filter(player_ids: int | list[int], *, season)`
— accepts one id or a list; single-id callers unchanged.

`players.py`: `resolve_players(inputs: list[str | int], index) ->
tuple[list[int], list[dict]]` — ints (or digit strings) pass through;
names go through `resolve_player`; failures collected as
`{"input": <original>, "error": <message>}` instead of raising; result ids
preserve input order and drop duplicates (first occurrence wins).

`shapes.py`: `shape_comparison(entries, league, week, schedules) -> list[dict]`
— one row per entry, built from the same helpers `shape_player_card` uses:

```json
{"player_id": 4242335, "name": "...", "position": "RB", "pro_team": "IND",
 "injury_status": "ACTIVE", "league_status": "ONTEAM", "owned_by": "My Matchup Team",
 "headshot_url": "...",
 "week": {"projected": 17.68, "opponent": "@KC", "kickoff": "2026-09-21T00:20:00Z"},
 "season": {"projected": 315.58, "points": 25.1, "positional_rank": 4, "games": 1, "avg": 25.1},
 "last_3": [25.1],
 "last_season": {"points": 362.3, "games": 4, "avg": 90.58},
 "percent_owned": 99.9, "percent_change": 0.0}
```
- `week.projected`: `_stat(period=week, source=1, season)`; `week.opponent/kickoff`: `game_context`.
- `season.games` = number of weekly actual entries this season (weeks with
  a stat line, including 0-point games); `avg = round(points/games, 2)` or
  null when games is 0. Same for `last_season` (null when no entry).
- `last_3`: this season's weekly actual points, newest first, max 3.
- `owned_by` is the team name string (not an object) — comparison rows are
  meant to be compact.
- Rows ordered by the caller (server passes ids in input order; unknown
  ids — requested but absent from the response — produce
  `{"player_id": id, "error": "ESPN returned no player with id N."}` rows).

`server.py`:
```python
@mcp.tool
def compare_players(players: list[str | int], week: int | None = None) -> dict[str, Any]:
```
- Validate 2 ≤ len ≤ 6 → else `ToolError("Pass between 2 and 6 players.")`;
  `week` 1..18 like `get_projections`.
- `ids, unresolved = resolve_players(players, _get_players_index(client))`
  (index fetched only if any input is a name).
- If fewer than 1 id resolved → `ToolError` listing the unresolved errors.
- `league = client.get("kona_playercard", "mTeam", "mStatus",
  fantasy_filter=player_card_filter(ids, season=...), scoring_period=week)`
  where `week` defaults to `league["status"]["currentMatchupPeriod"]` —
  which requires the week before the call: fetch it from
  `client.get("mStatus")` only when `week is None`. (Two small calls in the
  default case; one when `week` is given.)
- `rows = shape_comparison(ordered entries, league, week, _get_pro_schedules(client))`.
- Return `{"week": week, "players": rows, "unresolved": unresolved}`
  (`unresolved` omitted when empty).
- Docstring: use for "A or B?", start/sit between specific players, trade
  evaluation; inputs may mix names and ids; ambiguous names come back in
  `unresolved` with candidate ids — retry just those; `week` semantics as in
  `get_projections`; field meanings. INSTRUCTIONS: "For 'X or Y?' questions
  call compare_players with all the names at once rather than get_player
  repeatedly." List nine tools.

## Testing

Fixture `tests/fixtures/compare.json` (committed): `seasonId 2026`,
`scoringPeriodId 2`, `status.currentMatchupPeriod 1`, team 12; players
listed as [Compare Receiver (id 4361370, WR, NO, FREEAGENT, rank 6, own
99.37 / −0.01; stats 2026 wk1 28.2, wk2 proj 15.55, season proj 249.76,
season pts 28.2; 2025 wk18 0.0, wk17 25.9, wk2 11.4, season 268.0),
Compare Back (id 4242335, RB, IND, ONTEAM team 12, rank 4, own 99.91 / 0.0;
2026 wk1 25.1, wk2 proj 17.68, season proj 315.58, pts 25.1; 2025 wk18 5.9,
wk17 17.4, wk16 16.9, wk2 29.5, season 362.3)] — i.e. response order is the
reverse of the request order used in tests.

Tests: `player_card_filter` list form; `resolve_players` mixed
ids/names/ambiguous/unknown/duplicates with order preserved;
`shape_comparison` exact rows for both fixture players (request order
[4242335, 4361370] → Back first), `last_3`, games/avg, unknown id → error
row; tool: views + `scoringPeriodId=2` + filter ids, default-week path
makes the `mStatus` call first, 1-player and 7-player inputs → `ToolError`,
all-unresolved → `ToolError`, partial-unresolved → rows + `unresolved`;
nine tools registered.

Live: `compare_players(["Jonathan Taylor", "Chris Olave", "tucker"], week=2)`.
