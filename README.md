# fantasy-mcp

Gives Claude read-only access to your ESPN fantasy football team: your
roster, this week's matchup, free agents, and player profiles.

## Install in Claude Desktop

1. Download `fantasy-mcp.mcpb` from the
   [latest release](https://github.com/jolfr/fantasy-football-mcp/releases/latest).
2. Double-click the file (or in Claude Desktop: **Settings → Extensions →
   Install Extension…** and pick it).
3. Fill in the form: **espn_s2 cookie**, **SWID cookie**, and **League ID**.
   See [Get your ESPN cookies and league ID](#get-your-espn-cookies-and-league-id)
   below. Leave **Season** and **Team ID** blank unless you need them.
4. Start a new chat and ask "how's my fantasy team doing?"

The first launch takes a minute while Claude Desktop downloads Python and the
server's dependencies. Nothing else needs to be installed.

## Get your ESPN cookies and league ID

ESPN has no public API, so the server signs in with the same two cookies
your browser uses. They are private — do not share them.

### Chrome (or Edge, Brave)

1. Go to [fantasy.espn.com](https://fantasy.espn.com/football/) and make sure
   you're logged in.
2. Open DevTools: `Cmd+Option+I` on Mac, `F12` on Windows.
3. Click the **Application** tab. In the left sidebar, expand
   **Cookies** and click `https://fantasy.espn.com`.
4. Find the rows named `espn_s2` and `SWID`. Double-click each **Value** to
   select it, copy it, and paste it into the matching field in Claude
   Desktop. Keep the curly braces on `SWID`.

![Chrome DevTools showing the espn_s2 and SWID cookie rows](docs/images/chrome-cookies.png)

### Safari

1. Enable the Develop menu once: **Safari → Settings → Advanced → Show
   features for web developers**.
2. Go to [fantasy.espn.com](https://fantasy.espn.com/football/), logged in.
3. **Develop → Show Web Inspector**, then the **Storage** tab → **Cookies**
   → `fantasy.espn.com`.
4. Copy the **Value** of `espn_s2` and `SWID` as above.

### League ID

Open your league on fantasy.espn.com. The number after `leagueId=` in the
address bar is your League ID.

![Address bar showing leagueId= in the URL](docs/images/league-id.png)

### When cookies expire

ESPN cookies expire every few weeks. When they do, tools fail with a message
mentioning "cookies". Copy fresh values from your browser into
**Settings → Extensions → ESPN Fantasy Football** in Claude Desktop.

### Optional settings

- **Season** — defaults to the current calendar year. Set it explicitly from
  January to July if you want to keep looking at last season.
- **Team ID** — normally auto-detected from your SWID. Set it only if the
  server reports it can't find your team; it's the `teamId=` number in your
  team's URL.

## Use with Claude Code or other MCP clients

Clone the repo and install [uv](https://docs.astral.sh/uv/) (Python 3.12+).
`cp .env.example .env` and fill it in with the same values as above.

`.mcp.json` in this repo registers the server automatically when you run
`claude` here. For other projects or clients, add:

```json
{"mcpServers": {"fantasy": {"command": "uv",
  "args": ["run", "--directory", "/path/to/fantasy-mcp", "fantasy-mcp"]}}}
```

## Tools

- `whoami` — confirms auth; returns league name, season, your team.
- `get_league_settings` — scoring rules (with a one-line summary), lineup slots, position limits, playoff format, waiver and trade rules.
- `get_my_team` — your record, points, and roster with lineup slots.
- `get_matchup` — this week's head-to-head: live score, projection, win
  probability, and both rosters with per-player actual/projected points.
- `get_free_agents` — available players (free agents + waivers), optionally by
  position, sorted by % rostered or season projection, with ownership trend,
  projections, and positional rank.
- `get_player` — one player's full profile by name or id: league ownership,
  season totals/projection, ESPN outlook, and a per-week game log with stat
  lines for this season and last.

Nothing here can change your team; it is read-only.

## Develop

```bash
uv sync
uv run pytest
```

Build a local extension bundle to test in Claude Desktop:

```bash
npx -y @anthropic-ai/mcpb@2.1.2 pack . fantasy-mcp.mcpb
```

## Release

1. Bump `version` in both `pyproject.toml` and `manifest.json` (they must
   match — `tests/test_manifest.py` checks this).
2. Commit, then `git tag vX.Y.Z && git push origin main --tags`.
3. The `Release` workflow tests, packs, and attaches `fantasy-mcp.mcpb` to a
   GitHub Release for the tag.
