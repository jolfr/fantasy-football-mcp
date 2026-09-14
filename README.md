# fantasy-mcp

Gives Claude read-only access to your ESPN fantasy football team: your
roster, this week's matchup, free agents, and player profiles.

## Install in Claude Desktop

1. Download `fantasy-mcp.mcpb` (under **Assets**) from the
   [latest release](https://github.com/jolfr/fantasy-football-mcp/releases/latest).
2. Double-click the file (or in Claude Desktop: **Settings → Extensions →
   Advanced settings → Install Extension…** and pick it).
3. Claude Desktop will warn that the extension isn't signed by Anthropic —
   that's expected for this project; choose Install.
4. Fill in the form: **espn_s2 cookie**, **SWID cookie**, and **League ID**.
   See [Get your ESPN cookies and league ID](#get-your-espn-cookies-and-league-id)
   below. Leave **Season (optional)** and **Team ID (optional)** blank unless
   you need them.
5. Start a new chat and ask "how's my fantasy team doing?"

The first launch takes a minute while Claude Desktop downloads Python and the
server's dependencies. Nothing else needs to be installed.

## Get your ESPN cookies and league ID

ESPN has no public API, so the server signs in with the same two cookies
your browser uses. They are private — do not share them.

### Chrome (or Edge, Brave)

1. Go to [fantasy.espn.com](https://fantasy.espn.com/football/) and make sure
   you're logged in.
2. Open DevTools: right-click anywhere on the page and choose **Inspect**,
   or press `Cmd+Option+I` (Mac) / `F12` or `Ctrl+Shift+I` (Windows).
3. Click the **Application** tab. In the left sidebar, under **Storage**,
   expand **Cookies** and click `https://fantasy.espn.com`.
4. Find the rows named `espn_s2` and `SWID`. Click a row, then copy its
   **Value** from the box below the table. Leave **Show URL-decoded**
   unchecked — the decoded value won't work. Paste each into the matching
   field in Claude Desktop, keeping the curly braces on `SWID`.

### Safari (Mac)

1. Enable the Develop menu once: **Safari → Settings → Advanced → Show
   features for web developers**.
2. Go to [fantasy.espn.com](https://fantasy.espn.com/football/), logged in.
3. **Develop → Show Web Inspector**, then the **Storage** tab → **Cookies**
   → `fantasy.espn.com`.
4. Click the `espn_s2` row and copy its **Value**; then do the same for
   `SWID`.

### League ID

Open your league on fantasy.espn.com. The number after `leagueId=` in the
address bar is your League ID.

### When cookies expire

ESPN cookies expire every few weeks. When they do, tools fail with a message
mentioning "cookies". Copy fresh values from your browser into
**Settings → Extensions → ESPN Fantasy Football** in Claude Desktop.

### Optional settings

- **Season (optional)** — defaults to the current calendar year. Set it
  explicitly from January to July if you want to keep looking at last season.
- **Team ID (optional)** — normally auto-detected from your SWID. Set it only
  if the server reports it can't find your team; it's the `teamId=` number in
  your team's URL.

## Use with Claude Code or other MCP clients

Install [uv](https://docs.astral.sh/uv/) (Python 3.12+), then:

```bash
git clone https://github.com/jolfr/fantasy-football-mcp fantasy-mcp
cd fantasy-mcp
cp .env.example .env   # fill in the same values as above
uv sync
```

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
- `get_projections` — this (or any) week's ESPN projections for your roster with
  opponent/bye/kickoff, plus a suggested optimal lineup and the start/sit
  changes to reach it.
- `get_free_agents` — available players (free agents + waivers), optionally by
  position, sorted by % rostered or season projection, with ownership trend,
  projections, and positional rank.
- `get_player` — one player's full profile by name or id: league ownership,
  season totals/projection, ESPN outlook, and a per-week game log with stat
  lines for this season and last.
  In clients that support MCP Apps (Claude Desktop, claude.ai) this renders
  as an interactive card; elsewhere the JSON profile is returned as text.

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
