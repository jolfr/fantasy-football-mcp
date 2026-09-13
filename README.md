# fantasy-mcp

MCP server giving Claude read access to your ESPN fantasy football team.

## Setup

1. `cp .env.example .env`
2. Log in to fantasy.espn.com, open dev tools → Application → Cookies → `espn.com`,
   and copy `espn_s2` and `SWID` (keep the curly braces) into `.env`.
3. Set `ESPN_LEAGUE_ID` (from your league URL: `leagueId=...`).
4. Optional: `ESPN_SEASON` (defaults to the current calendar year — set it
   explicitly during playoffs/offseason, Jan–Jul) and `ESPN_TEAM_ID` (skips
   auto-detecting your team from your SWID).
5. `uv sync` (requires [uv](https://docs.astral.sh/uv/) and Python 3.12+)

ESPN cookies expire periodically. When they do, tools fail with a message
mentioning "cookies" — re-copy `espn_s2` and `SWID` from your browser.

## Use with Claude Code

`.mcp.json` in this repo registers the server automatically when you run
`claude` here. For other projects or Claude Desktop, add:

```json
{"mcpServers": {"fantasy": {"command": "uv",
  "args": ["run", "--directory", "/path/to/fantasy-mcp", "fantasy-mcp"]}}}
```

## Tools

- `whoami` — confirms auth; returns league name, season, your team.
- `get_my_team` — your record, points, and roster with lineup slots.

## Develop

`uv run pytest`
