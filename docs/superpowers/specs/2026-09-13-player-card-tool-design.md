# `get_player` Tool — Design

**Date:** 2026-09-13
**Status:** Approved
**Builds on:** basic, matchup, and free-agents designs (same date)

## Goal

Add `get_player(name | player_id)` returning a high-fidelity profile for one
player: bio/status, who rosters them in the user's league, ownership, season
totals and projection, ESPN's written outlook, expert positional rank, and a
per-week game log with actual points, projection, and a named stat line
(yards, TDs, targets, FGs, sacks, …) for this season and last.

Also: add `player_id` to the rows returned by `get_my_team`, `get_matchup`,
and `get_free_agents` so Claude can chain precisely.

## Scope

In:
- `get_player(name: str | None, player_id: int | None)` — exactly one required
- Name resolution against ESPN's league-independent active-player index
- New modules: `players.py` (name resolution), `stats.py` (stat-id names)
- `EspnClient.get_players_index()` — the one client addition
- `player_id` field on existing roster/free-agent rows

Out (later): player news articles/video, trade-value metrics, opponent/
matchup ratings (`positionAgainstOpponent`), defensive points-allowed
bucket stats (derivable from `points_allowed`), IDP stat ids, refreshing the
name index without a server restart.

## ESPN facts (verified live 2026-09-13)

- **Player index:** `GET {BASE}/seasons/{season}/players?scoringPeriodId=0&
  view=players_wl` with header `X-Fantasy-Filter: {"filterActive":
  {"value": true}}` (same cookies). Returns a JSON **list** of ~2,600 active
  players: `{id, fullName, firstName, lastName, defaultPositionId,
  proTeamId, eligibleSlots, ownership, ...}`. ~650 KB, ~0.5 s. No league id.
- **No server-side name search** on any league view (`filterName` etc. are
  rejected) — hence the index.
- **Player card:** league endpoint, views `kona_playercard`, `mTeam`,
  `mStatus` together, header filter
  ```json
  {"players": {"filterIds": {"value": [<id>]},
               "filterStatsForTopScoringPeriodIds": {
                   "value": 17,
                   "additionalValue": ["00<season>", "10<season>",
                                       "00<season-1>",
                                       "11<season>1", ..., "11<season>18"]}}}
  ```
  Response has `players` (one entry), `teams` (all league teams), `status`,
  `scoringPeriodId`, `seasonId`.
- Entry: `onTeamId` (0 = not rostered), `status` (`ONTEAM`|`FREEAGENT`|
  `WAIVERS`), `ratings["0"].positionalRanking` (0 = unranked),
  `player.{fullName, defaultPositionId, proTeamId, injuryStatus, injured,
  eligibleSlots, seasonOutlook, ownership.{percentOwned, percentStarted,
  percentChange, averageDraftPosition}, stats[]}`.
- `stats[]` items: `seasonId`, `scoringPeriodId` (0 = season total),
  `statSourceId` (0 actual / 1 projected), `appliedTotal`, `stats`
  (raw `{stat_id: value}`), `appliedStats` (`{stat_id: points}` for scoring
  stats only). Weekly **actuals** come back for every played week of the
  current and prior season; weekly **projections** only for weeks ESPN has
  published (currently just the current week). Prior-season season-total
  entries share keys with current-season ones — always match `seasonId`.
- Stat-id semantics were confirmed by dividing `appliedStats` points by the
  league's scoring (e.g. id 3 = 163 → 6.52 pts = passing yards / 25; id 72 =
  1 → −2 pts = fumble lost; id 77 = 1 → 4 pts = FG 40–49; id 99 = 2 → 2 pts
  = sacks; id 95 = 1 → 2 pts = interception) and against community
  documentation of ESPN's ids. Ids not confirmed are left unmapped.

## Layout changes

```
src/fantasy_mcp/
├── espn.py      # + get_players_index()
├── players.py   # NEW: resolve_player(name, index) -> int
├── stats.py     # NEW: STAT_NAMES + shape_stat_line()
├── shapes.py    # + shape_player_card(); player_id added to existing rows
├── server.py    # + get_player tool; index cache
tests/
├── test_players.py, test_stats.py        # NEW
├── test_espn.py, test_shapes.py, test_server.py  # extended
└── fixtures/player_card.json, players_index.json  # NEW (trimmed real data)
```

## `espn.py`

```python
def get_players_index(self) -> list[dict[str, Any]]:
    """Active players for the season (league-independent); ~2.6k entries."""
```
`GET f"{BASE}/seasons/{season}/players"`, params `scoringPeriodId=0`,
`view=players_wl`, header `X-Fantasy-Filter: {"filterActive": {"value": true}}`,
same cookies/timeout/`_parse` error mapping. `_parse` currently returns
`dict`; generalize its return annotation to `Any` (body may be a list). A
non-list body → `EspnError("Unexpected players index response")`.

## `players.py` (pure)

```python
def resolve_player(name: str, index: list[dict]) -> int:
```
1. Normalize both sides: casefold, strip, collapse whitespace, drop periods
   and apostrophes (`"A.J. Brown"` == `"aj brown"`, `"Ja'Kobi"` == `"jakobi"`).
2. Exact match on normalized `fullName` → if exactly one, return its `id`.
3. Else substring match (normalized query in normalized `fullName`).
4. Exactly one hit → `id`. Zero → `EspnError(f"No active player matches
   {name!r}.")`. Several → `EspnError` listing up to 8 candidates as
   `"Full Name (POS, TEAM, id 12345)"` sorted by `ownership.percentOwned`
   desc, and instructing to retry with `player_id` or a fuller name.
   Exact-match ties (two players with identical names) also go this route.

`players.py` imports `ids` (for POS/TEAM names) and `EspnError` only.

## `stats.py` (data)

`STAT_NAMES: dict[int, str]` — snake_case names:

| ids | names |
|-----|-------|
| 0, 1, 3, 4, 19, 20 | pass_att, pass_comp, pass_yds, pass_td, pass_2pt, pass_int |
| 23, 24, 25, 26 | rush_att, rush_yds, rush_td, rush_2pt |
| 58, 53, 42, 43, 44 | targets, receptions, rec_yds, rec_td, rec_2pt |
| 68, 72 | fumbles, fumbles_lost |
| 74, 77, 80, 83, 84, 85, 86, 87, 88 | fg_made_50_plus, fg_made_40_49, fg_made_under_40, fg_made, fg_att, fg_missed, xp_made, xp_att, xp_missed |
| 95, 96, 97, 98, 99 | dst_int, dst_fumble_rec, dst_blocked_kicks, dst_safeties, dst_sacks |
| 93, 101, 102, 103, 104 | dst_blocked_kick_td, dst_kick_return_td, dst_punt_return_td, dst_fumble_return_td, dst_int_return_td |
| 120, 127 | dst_points_allowed, dst_yards_allowed |
| 155, 156, 210 | team_win, team_loss, games_played |

```python
def shape_stat_line(raw: dict[str, Any] | None) -> dict[str, float]:
    """Map {stat_id: value} to {name: value}; drop unmapped ids and zeros."""
```
Keys of `raw` are strings (ESPN JSON); values cast to `float` then to `int`
when integral (so `19.0` → `19`, `5.158` stays). Returns `{}` for `None`.

## `shapes.py`

`player_id` added to rows:
- `_shape_player(entry)`: `"player_id": entry.get("playerId")` (roster
  entries carry `playerId`; fallback `playerPoolEntry.id`).
- `shape_free_agent(entry, ...)`: `"player_id": entry.get("id")`.

New:

```python
def shape_player_card(entry: dict, league: dict) -> dict:
```
`season = league.get("seasonId")`, `period = league.get("scoringPeriodId")`.

```json
{
  "player_id": 4242335,
  "name": "Jonathan Taylor",
  "position": "RB", "pro_team": "IND",
  "injury_status": "ACTIVE", "injured": false,
  "eligible_slots": ["RB", "RB/WR", "FLEX", "OP"],      // ids.LINEUP_SLOTS, BENCH/IR omitted
  "league_status": "ONTEAM",                            // entry.status
  "owned_by": {"team_id": 12, "name": "Jack's Jubilant Team"} | null,
  "ownership": {"percent_owned": 99.9, "percent_started": 99.6,
                "percent_change": 0.0, "adp": 6.4},     // rounded 1; null if absent
  "season": {"year": 2026, "projected": 315.58, "points": 25.1,
             "positional_rank": 4},                     // 0 → null
  "last_season": {"year": 2025, "points": 362.3},       // null if no entry
  "outlook": "Taylor enters the 2026 season ...",        // null if absent/empty
  "game_log": [
    {"season": 2026, "week": 1, "points": 25.1, "projected": 17.75,
     "stats": {"rush_att": 19, "rush_yds": 98, "rush_td": 2, "targets": 4,
               "receptions": 3, "rec_yds": 23, "fumbles_lost": 1, ...}},
    {"season": 2025, "week": 18, "points": 5.9, "projected": null, "stats": {...}},
    ...
  ]
}
```
- `owned_by`: `_find_team(league, onTeamId)`; null when `onTeamId` is 0 or
  the team is absent.
- `game_log`: one row per `stats[]` item with `statSourceId == 0` and
  `scoringPeriodId > 0`, for `seasonId in (season, season - 1)`. `projected`
  is the `statSourceId == 1` item for the same season/week if present.
  Sorted by (season desc, week desc). `stats` via `shape_stat_line(item.stats)`.
- All `_stat` lookups pass the explicit season.

## `server.py`

```python
_players_index: list[dict[str, Any]] | None = None

def _get_players_index(client) -> list[dict[str, Any]]:   # fetch once per process
def set_players_index_for_tests(index | None)

@mcp.tool
def get_player(name: str | None = None, player_id: int | None = None) -> dict[str, Any]:
    try:
        if (name is None) == (player_id is None):
            raise ToolError("Pass exactly one of name or player_id.")
        client = _get_client()
        if player_id is None:
            player_id = resolve_player(name, _get_players_index(client))
        season = client.settings.season
        fantasy_filter = player_card_filter(player_id, season)   # in filters.py
        league = client.get("kona_playercard", "mTeam", "mStatus", fantasy_filter=fantasy_filter)
        entries = league.get("players", [])
        if not entries:
            raise EspnError(f"ESPN returned no player with id {player_id}.")
        return shape_player_card(entries[0], league)
    except (FilterError, EspnError, ConfigError) as e:
        raise ToolError(str(e)) from e
```
`filters.player_card_filter(player_id: int, season: int) -> dict` builds the
header JSON shown in ESPN facts (fresh dict per call).

Docstring: when to use ("tell me about X", "how has X been doing", "who has
X in my league", "is X worth a waiver claim"); pass `name` (full name best;
partial OK if unique) or `player_id` from another tool's row; field meanings
(`league_status`/`owned_by`, `ownership.percent_change` trend, `season` vs
`last_season`, `game_log` newest first, `stats` are raw counts not points,
`projected` null when ESPN hasn't published it); limits (no news text, no
opponent ratings). `INSTRUCTIONS`: add "Use get_player for questions about a
specific player (history, outlook, who owns them); prefer passing player_id
from another tool's output when you have it." List five tools.

## Errors

All `EspnError` (incl. resolution failures), `FilterError`, `ConfigError`
→ `ToolError`. Argument-combination error raised directly as `ToolError`.
Ambiguity message must include candidates with ids so the model can
self-correct in one step.

## Testing

Fixtures (trimmed real data, names scrubbed to placeholders):
- `tests/fixtures/players_index.json`: 6 entries — "Tre Tucker" (WR, LV),
  "Tucker Kraft" (TE, GB), "Justin Tucker" (K), "A.J. Brown" (WR, id 1001),
  "Jonathan Taylor" (RB, id 4242335), and a duplicate-name pair "Sam Smith"
  ×2 — each with `id`, `fullName`, `defaultPositionId`, `proTeamId`,
  `ownership.percentOwned`.
- `tests/fixtures/player_card.json`: `{"seasonId": 2026, "scoringPeriodId":
  1, "teams": [team 12 "My Matchup Team"], "players": [one RB entry]}` with
  `onTeamId 12`, `status ONTEAM`, ratings rank 4, outlook text, ownership,
  `eligibleSlots [2, 3, 23, 7, 20, 21]`, stats: 2026 wk1 actual (with raw
  `stats` for rush/rec/fumble ids) + wk1 projection, 2026 season actual +
  projection, 2025 season actual, 2025 wk18 and wk17 actuals, plus a 2024
  decoy season total that must be ignored.

`tests/test_players.py`: exact match; casefold + punctuation ("a.j. brown" →
1001); unique substring ("kraft"); ambiguous substring ("tucker") → error
listing all three with ids, sorted by ownership; duplicate exact names →
error; no match → error.

`tests/test_stats.py`: maps known ids and drops unknown/zero; integral floats
become ints; `None` → `{}`.

`tests/test_filters.py`: `player_card_filter` exact dict incl. 21
`additionalValue` ids.

`tests/test_espn.py`: `get_players_index` hits the players URL with view/
scoringPeriodId params, cookies, and the filterActive header; list body
returned; dict body → `EspnError`.

`tests/test_shapes.py`: `shape_player_card` exact dict for the fixture (game
log order 2026-1, 2025-18, 2025-17; projection attached only to 2026-1;
2024 decoy ignored; `owned_by` resolved; rank/outlook/eligible slots);
`onTeamId 0` → `owned_by` null; existing row tests updated for `player_id`.

`tests/test_server.py`: `get_player(name=...)` path (index injected via
`set_players_index_for_tests`; asserts views + header JSON); `player_id`
path skips the index; neither/both args → `ToolError`; ambiguous name →
`ToolError` containing a candidate id; empty `players` → `ToolError`.

Manual: live `get_player(name="Jayden Daniels")` and `get_player(
player_id=4242335)`; cross-check week-1 stat lines against ESPN's box score
(17/32, 163 yds, 1 TD, 5 rush / 31 for Daniels; 19/98/2 + 3 rec 23 yds on 4
targets for Taylor; 2/2 FG incl. one 50+, 5/5 XP for Loop; 2 sacks, 1 INT,
1 FR, 23 pts allowed for BAL D/ST). Any mismatch → fix `STAT_NAMES` before
merge.
