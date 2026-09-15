# `get_transactions` Tool — Design

**Date:** 2026-09-15
**Status:** Approved

## Goal

League transaction log — adds, drops, waiver claims (incl. pending), trades
— newest first, filterable by team, with a one-line summary each.

## Verified facts (2026-09-15, live)

- View `mTransactions2` (+ `mTeam` for team names) returns `transactions[]`:
  `id, type, status, teamId, scoringPeriodId, bidAmount, proposedDate
  (epoch ms), processDate (epoch ms | null), isPending, memberId, items[]`.
  Observed types/statuses: `ROSTER/EXECUTED` (items all `LINEUP`, or a lone
  `DROP`), `WAIVER/PENDING` (items `ADD` [+ `DROP`]). Other ESPN types:
  `FREEAGENT`, `TRADE_PROPOSAL`, `TRADE_ACCEPT`, `TRADE_DECLINE`,
  `TRADE_VETO`, `DRAFT`.
- `items[]`: `type` (`ADD|DROP|LINEUP|TRADE|DRAFT`), `playerId`,
  `fromTeamId`, `toTeamId` (0 = free agency), `fromLineupSlotId`,
  `toLineupSlotId` (-1 = n/a). No player names → resolve via the cached
  player index (`id → fullName, defaultPositionId, proTeamId`).
- `mPendingTransactions` is a subset of the above; not needed.

## Changes

`schedules._iso` → moved to `shapes._iso_utc(epoch_ms)` with
`timespec="seconds"` (schedules imports it); existing kickoff output is
unchanged (whole seconds).

`shapes.py`:
```python
def shape_transactions(league, index_by_id, *, team_id=None, limit=25,
                       include_lineup_moves=False) -> dict
```
Output:
```json
{"week": 2,
 "transactions": [
   {"id": "...", "type": "WAIVER", "status": "PENDING", "week": 2,
    "team": {"team_id": 12, "name": "My Matchup Team"},
    "proposed": "2026-09-15T11:08:35Z", "processed": "2026-09-16T07:00:00Z", "bid": 7,
    "items": [{"action": "ADD", "player_id": 4696044, "name": "...", "position": "WR",
               "pro_team": "JAX", "from_team": null, "to_team": "My Matchup Team",
               "from_slot": null, "to_slot": null}, ...],
    "summary": "Waiver claim pending ($7): add X, drop Y"}]}
```
- `type` normalized: `TRADE_*` → `TRADE` with `status` carrying
  ACCEPTED/DECLINED/VETOED/PROPOSED when derivable (`TRADE_ACCEPT` →
  `TRADE`/`EXECUTED` stays as ESPN's status; the original ESPN type is kept
  in `espn_type`). `ROSTER` with only `LINEUP` items → `LINEUP`; `ROSTER`
  with adds/drops → `FREEAGENT`.
- Player fields from the index; unknown id → name null, position/pro_team
  `UNKNOWN_-1`.
- `from_team`/`to_team`: team name via `_find_team`, null when 0/absent.
  `from_slot`/`to_slot`: `ids.LINEUP_SLOTS` name, null when -1/absent.
- `summary`: `"{Waiver claim|Free agent move|Trade|Lineup change|Draft pick}
  {pending|executed|declined|vetoed}{ ($bid)}: add A, drop B"`; trades:
  `"Trade executed: My Matchup Team sends X; Rival Team sends Y"`; lineup:
  `"Lineup change: X to FLEX, Y to RB"`.
- Filter: `team_id` keeps transactions whose `teamId` matches OR any item's
  from/to team matches (so the other side of a trade sees it). Lineup-only
  transactions excluded unless `include_lineup_moves`. Sort by
  `proposedDate` desc; truncate to `limit`.
- Tolerant of missing keys; `{}` → `{"week": None, "transactions": []}`.

`server.py`:
```python
@mcp.tool
def get_transactions(team: str | int | None = None, limit: int = 25,
                     include_lineup_moves: bool = False) -> dict[str, Any]:
```
- `limit` 1–100 else `ToolError`; `league = client.get("mTransactions2",
  "mTeam")`; team via `team_by_id` / `find_team_by_name`; index via
  `_get_players_index` (only if any transaction has items);
  `index_by_id = {p["id"]: p ...}`.
- Docstring: when to use ("who dropped X", "did my claim go through",
  recent trades, waiver activity), that pending claims appear with
  `status PENDING` and `processed` = when they'll run, that lineup moves are
  hidden by default. INSTRUCTIONS: "Use get_transactions for adds, drops,
  trades, and waiver claims (pending ones included)"; remove "There is no
  transaction data yet"; eleven tools.

## Testing

Fixture `tests/fixtures/transactions.json` (committed): teams 12/5; four
transactions — lineup move (team 5), pending waiver (team 12, bid 7, ADD
4696044 + DROP 103, processDate set), executed FREEAGENT add 4572680 / drop
4362628 (team 5), TRADE_ACCEPT (12 sends 4242335 to 5; 5 sends 1001 to 12).
Index fixture `players_index.json` names 4572680 (Tucker Kraft), 4362628
(Tre Tucker), 4242335 (Jonathan Taylor), 1001 (A.J. Brown); 4696044/101/
102/103 are unknown → null names.

Tests: `_iso_utc` seconds precision; default call → 3 rows (lineup hidden)
newest first with exact waiver row and trade summary; `include_lineup_moves`
→ 4 with lineup summary; `team_id=5` → includes the trade and both team-5
moves; `limit=1`; sparse; tool: views `["mTransactions2","mTeam"]`, team by
name, bad limit → ToolError, index fetched once; eleven tools.

Live: `get_transactions()` shows the three pending claims with names.
