# ESPN Fantasy Football MCP — Basic Design

**Date:** 2026-09-13
**Status:** Approved

## Goal

A local MCP server (stdio) so Claude can read the user's ESPN fantasy
football team data. First milestone: get authentication against a
*private* league working and expose the user's roster.

## Scope (v0.1)

In:
- Auth via `espn_s2` + `SWID` cookies loaded from env / `.env`
- Tool `whoami` — smoke test that auth works
- Tool `get_my_team` — the user's team record and roster

Out (later milestones): matchups, standings, free agents, transactions,
historical seasons (`leagueHistory` endpoint), any write operations.

## References

- https://ffscrapr.ffverse.com/articles/espn_getendpoint.html
- https://stmorse.github.io/journal/espn-fantasy-v3.html

## Stack

Python 3.12, `uv`, `fastmcp` (already declared), `httpx`,
`python-dotenv`. Dev: `pytest`, `respx`.

## Layout

```
fantasy-mcp/
├── src/fantasy_mcp/
│   ├── __init__.py
│   ├── server.py      # FastMCP app + tool definitions; main() entrypoint
│   ├── espn.py        # EspnClient
│   ├── config.py      # Settings from env / .env
│   └── ids.py         # ESPN ID -> name maps
├── tests/
│   ├── fixtures/      # trimmed, scrubbed ESPN JSON
│   └── test_*.py
├── .env.example
└── pyproject.toml     # [project.scripts] fantasy-mcp = "fantasy_mcp.server:main"
```

Root `main.py` is removed.

## Configuration (`config.py`)

Loaded from environment, with `.env` fallback via `python-dotenv`.

| Var              | Required | Notes                                              |
|------------------|----------|----------------------------------------------------|
| `ESPN_S2`        | yes      | Long session cookie                                |
| `ESPN_SWID`      | yes      | Includes curly braces, e.g. `{ABC-...}`            |
| `ESPN_LEAGUE_ID` | yes      | Integer                                            |
| `ESPN_SEASON`    | no       | Defaults to current calendar year                  |
| `ESPN_TEAM_ID`   | no       | If unset, resolved by matching SWID to team owners |

Startup fails fast with a message naming every missing required var.
`.env` is gitignored; `.env.example` documents the keys.

## ESPN client (`espn.py`)

```
base_url = https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl
           /seasons/{season}/segments/0/leagues/{league_id}
```

`EspnClient(settings)`:

- `get(*views: str, filter: dict | None = None) -> dict`
  - single `httpx.get(base_url, params=[("view", v) for v in views],
    cookies={"espn_s2": ..., "SWID": ...}, headers=...)`
  - if `filter` given, send as `X-Fantasy-Filter: <json>` header
  - timeout 15s
- `find_my_team_id() -> int`
  - returns `ESPN_TEAM_ID` if configured
  - else calls `get("mTeam")`, returns the `id` of the team whose
    `owners[]` contains the configured SWID (case-insensitive compare)
  - raises `EspnError` if no team matches

Errors (all subclass `EspnError(Exception)`):

| Class               | When                                                        |
|---------------------|-------------------------------------------------------------|
| `EspnAuthError`     | HTTP 401/403, **or** 200 with non-JSON body (ESPN login page)|
| `EspnNotFoundError` | HTTP 404 (bad league id / season)                           |
| `EspnError`         | any other non-2xx; message includes status + body[:200]     |

Auth error message tells the user their cookies are missing/expired.

## ID maps (`ids.py`)

Three `dict[int, str]` tables: `POSITIONS` (defaultPositionId),
`LINEUP_SLOTS` (lineupSlotId), `PRO_TEAMS` (proTeamId). Helper
`name(table, id) -> str` returns `f"UNKNOWN_{id}"` for missing keys.

## Tools (`server.py`)

### `whoami()`
Calls `get("mTeam")`. Returns:
```json
{"league_id": 123, "season": 2026, "league_name": "...",
 "team_id": 3, "team_name": "..."}
```

### `get_my_team()`
Calls `get("mTeam", "mRoster")`, selects team by `find_my_team_id()`.
Returns:
```json
{
  "team_id": 3,
  "name": "...", "abbrev": "...",
  "record": {"wins": 1, "losses": 0, "ties": 0},
  "points_for": 128.4, "points_against": 101.2,
  "roster": [
    {"name": "Josh Allen", "position": "QB", "slot": "QB",
     "pro_team": "BUF", "injury_status": "ACTIVE"}
  ]
}
```
Source paths: `teams[i].name`, `.abbrev`, `.record.overall.{wins,
losses,ties,pointsFor,pointsAgainst}`, `.roster.entries[].lineupSlotId`,
`.roster.entries[].playerPoolEntry.player.{fullName, defaultPositionId,
proTeamId, injuryStatus}`.

Roster sorted by lineup slot id (starters first, bench/IR last).

Tool errors: `EspnError` subclasses propagate as tool errors with their
message so Claude can relay "cookies expired" etc. to the user.

## Testing

`pytest` + `respx` mocking `httpx`. No live network in tests.
Fixtures: real `mTeam`/`mRoster` responses captured once, trimmed to one
or two teams, SWIDs and names scrubbed.

Cases:
- cookies attached to request; `view` params repeated correctly
- `X-Fantasy-Filter` header sent when `filter` given
- `find_my_team_id`: env override; SWID match; no match -> error
- 401/403 -> `EspnAuthError`; 200 HTML -> `EspnAuthError`; 404 ->
  `EspnNotFoundError`; 500 -> `EspnError`
- `ids.name` fallback
- `get_my_team` shape against fixture
- config: missing vars listed in error; season default

Manual verification: `uv run fantasy-mcp` registered in Claude Code, then
ask Claude to run `whoami`.

## Running

`.mcp.json` / Claude Desktop config:
```json
{"mcpServers": {"fantasy": {"command": "uv",
  "args": ["run", "--directory", "/path/to/fantasy-mcp", "fantasy-mcp"]}}}
```
Cookies come from `.env` in the project dir.
