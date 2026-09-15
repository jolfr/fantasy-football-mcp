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
4. Skip the settings form (leave it empty and click Save) — you'll do setup in chat.
5. Start a new chat and say **set up my fantasy league**. A card walks you
   through copying two cookies from your browser and your league ID, then
   tests the connection.
6. Ask "how's my fantasy team doing?"

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
   box in the setup card (or the settings form), keeping the curly braces
   on `SWID`.

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

### Prefer not to type cookies in chat?

Enter them in **Settings → Extensions → ESPN Fantasy Football** instead;
Claude Desktop keeps them in your keychain. Values saved from the chat card
take precedence over the settings form.

### When cookies expire

ESPN cookies expire every few weeks. When they do, tools fail with a message
mentioning "cookies". Say **update my ESPN cookies** and fill in the card
again (or update the settings form if you used that).

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

If you also use Claude Desktop, values saved from the in-chat setup card
(`~/Library/Application Support/fantasy-mcp/config.json` on macOS,
`~/.config/fantasy-mcp/config.json` on Linux, `%LOCALAPPDATA%\fantasy-mcp\config.json`
on Windows) take precedence over `.env`.

## Tools

- `whoami` — confirms auth; returns league name, season, your team.
- `setup` — shows the in-chat setup card; `save_settings` stores and
  verifies what you enter.
- `get_league_settings` — scoring rules (with a one-line summary), lineup slots, position limits, playoff format, waiver and trade rules.
- `get_standings` — every team's rank, record, points, streak, ESPN projected
  finish, waiver priority, transaction counts, and playoff clinch status.
- `get_my_team` — your record, points, and roster with lineup slots.
- `get_team` — any other team's roster by id, name, or abbreviation, with owner
  and current-week projections (trade targets, positional depth).
- `get_matchup` — head-to-head for the current week (or any `week`): live score,
  projection, win probability, and both rosters with per-player actual/projected points.
- `get_projections` — this (or any) week's ESPN projections for your roster with
  opponent/bye/kickoff, plus a suggested optimal lineup and the start/sit
  changes to reach it.
- `get_free_agents` — available players (free agents + waivers), optionally by
  position, sorted by % rostered or season projection, with ownership trend,
  projections, and positional rank.
- `get_transactions` — league transaction log (adds, drops, trades, waiver
  claims including pending ones), newest first, optionally filtered to one
  team, with a one-line summary per transaction.
- `get_player` — one player's full profile by name or id: league ownership,
  season totals/projection, ESPN outlook, and a per-week game log with stat
  lines for this season and last.
  In clients that support MCP Apps (Claude Desktop, claude.ai) this renders
  as an interactive card; elsewhere the JSON profile is returned as text.
- `compare_players` — 2–6 players side by side: this week's projection and opponent, season pace, recent form, last season, league availability, ownership trend.

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
