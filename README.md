# fantasy-mcp

MCP server giving Claude read access to your ESPN fantasy football team.

## Setup

1. `cp .env.example .env`
2. Log in to fantasy.espn.com, open dev tools → Application → Cookies → `espn.com`,
   and copy `espn_s2` and `SWID` (keep the curly braces) into `.env`.
3. Set `ESPN_LEAGUE_ID` (from your league URL: `leagueId=...`).
4. `uv sync`

## Use with Claude Code

`.mcp.json` in this repo registers the server automatically when you run
`claude` here. For other projects or Claude Desktop, add:

```json
{"mcpServers": {"fantasy": {"command": "uv",
  "args": ["run", "--directory", "/Users/jcarroll/Repositories/fantasy-mcp", "fantasy-mcp"]}}}
```

## Tools

- `whoami` — confirms auth; returns league name, season, your team.
- `get_my_team` — your record, points, and roster with lineup slots.

## Develop

`uv run pytest`
