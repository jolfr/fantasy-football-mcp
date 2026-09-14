# Claude Desktop Distribution (.mcpb) — Design

**Date:** 2026-09-14
**Status:** Approved

## Goal

Let a non-technical league member install fantasy-mcp in Claude Desktop by
downloading one file and filling in a form — no Python, uv, git, or terminal.
Claude Code users keep the existing clone-and-`uv run` path.

## Scope

In:
- `manifest.json` (MCPB v0.4, `server.type = "uv"`) with a `user_config` form
  for ESPN credentials
- `.mcpbignore`
- Text-only edits to the two messages that currently name `.env`
- `.github/workflows/release.yml`: on a `v*` tag, test, validate, pack, and
  attach `fantasy-mcp.mcpb` to a GitHub Release
- README restructured around the Desktop path, with an illustrated
  "get your ESPN cookies" walkthrough (`docs/images/`)

Out (later): PyPI / `uvx` publishing; bundle signing; an extension icon;
CI on pull requests; a cookie-grabbing bookmarklet; an `install` CLI for
other clients.

## Verified facts (2026-09-14, mcpb CLI 2.1+, manifest 0.4)

- `server.type = "uv"` makes Claude Desktop download Python, create a venv,
  and install deps from `pyproject.toml` at the bundle root. No user-side
  Python or uv. An Anthropic maintainer confirmed (mcpb issue #84,
  2026-03-12) that this bypasses the "incompatible with your device" check
  that blocks `python`-type bundles without system Python. Still labeled
  experimental.
- `mcpb validate` / `mcpb pack` still require `server.mcp_config` even for
  `uv` (issue #263), so we include one, exactly like the official
  `examples/hello-world-uv`.
- `user_config` fields are injected via `${user_config.KEY}` into
  `mcp_config.env` (or `args`). `sensitive: true` stores the value in the OS
  keychain and masks it in the form.
- `config.py` already reads env vars before `.env`; the only change needed was
  treating unresolved `${...}` placeholders as unset (see Resolved note in
  section 1).

## 1. Bundle layout

The repo root is the bundle. New files:

### `manifest.json`

```json
{
  "manifest_version": "0.4",
  "name": "fantasy-mcp",
  "display_name": "ESPN Fantasy Football",
  "version": "<same as pyproject.toml>",
  "description": "Read-only access to your ESPN fantasy football team, matchup, free agents, and players.",
  "author": { "name": "Thomas Jack Carroll" },
  "license": "GPL-2.0",
  "server": {
    "type": "uv",
    "entry_point": "src/fantasy_mcp/server.py",
    "mcp_config": {
      "command": "uv",
      "args": ["run", "--directory", "${__dirname}", "fantasy-mcp"],
      "env": {
        "ESPN_S2": "${user_config.espn_s2}",
        "ESPN_SWID": "${user_config.swid}",
        "ESPN_LEAGUE_ID": "${user_config.league_id}",
        "ESPN_SEASON": "${user_config.season}",
        "ESPN_TEAM_ID": "${user_config.team_id}"
      }
    }
  },
  "user_config": {
    "espn_s2":   { "type": "string", "title": "espn_s2 cookie", "sensitive": true, "required": true,
                   "description": "From your browser's cookies for espn.com while logged in. See README: Get your ESPN cookies." },
    "swid":      { "type": "string", "title": "SWID cookie", "sensitive": true, "required": true,
                   "description": "Same place as espn_s2. Keep the curly braces." },
    "league_id": { "type": "number", "title": "League ID", "required": true,
                   "description": "The leagueId=... number in your league's URL on fantasy.espn.com." },
    "season":    { "type": "number", "title": "Season (optional)", "required": false,
                   "description": "Defaults to the current calendar year. Set during Jan-Jul to keep looking at last season." },
    "team_id":   { "type": "number", "title": "Team ID (optional)", "required": false,
                   "description": "Leave blank to auto-detect your team from your SWID." }
  },
  "compatibility": {
    "platforms": ["darwin", "win32", "linux"],
    "runtimes": { "python": ">=3.12" }
  },
  "keywords": ["espn", "fantasy", "football", "nfl"]
}
```

Resolved 2026-09-14 in the end-to-end test: Desktop does not store blank
optional fields at all and passes the `${user_config.season}` template
through literally. `config.py` treats blank or unresolved `${...}` values as
unset (`_env`).

### `.mcpbignore`

```
.git/
.github/
.venv/
.claude/
.pytest_cache/
.ruff_cache/
__pycache__/
tests/
docs/
.env
.env.*
!.env.example
*.mcpb
```

`uv.lock` is included so users get the exact dependency set that was tested.

### Versioning

`pyproject.toml` `[project].version` and `manifest.json` `version` are always
identical; the release workflow enforces it against the git tag.

## 2. Server changes

Text only. No new modules, dependencies, or runtime branching.

- `server.py` `INSTRUCTIONS`, last paragraph: replace "into the server's
  `.env` file" with "into wherever the server is configured: the extension's
  settings in Claude Desktop (Settings → Extensions → ESPN Fantasy Football),
  or the `.env` file for a local checkout."
- `config.py` `ConfigError` message: "Set them in the extension's settings in
  Claude Desktop, or copy `.env.example` to `.env` and fill them in."
- `config.py`: `_env()` helper — unset, blank, or unresolved `${...}`
  template values count as not set, for required and optional vars alike.

`EspnAuthError` messages already say "refresh them from your browser" and do
not name `.env`; unchanged. `load_dotenv()` in the bundle directory finds no
`.env`; harmless.

## 3. Release workflow

`.github/workflows/release.yml`, `on: push: tags: ['v*']`,
`permissions: contents: write`:

1. `actions/checkout`, `actions/setup-node` (LTS), `astral-sh/setup-uv`.
2. Version guard (shell): `TAG=${GITHUB_REF_NAME#v}`; read the version from
   `pyproject.toml` and `manifest.json`; fail unless all three match.
3. `uv sync --locked && uv run pytest`.
4. `npx @anthropic-ai/mcpb validate manifest.json`
5. `npx @anthropic-ai/mcpb pack . fantasy-mcp.mcpb`, list the bundle contents,
   and fail if the listing contains tests/, docs/, .venv/, .git/, .worktrees/,
   or .env
6. `gh release create "$GITHUB_REF_NAME" fantasy-mcp.mcpb --generate-notes`
   (uses `GITHUB_TOKEN`).

Unsigned for now. Nothing runs on ordinary pushes.

Cutting a release: bump the version in both files, commit, `git tag vX.Y.Z`,
`git push --tags`.

## 4. README

New order:

1. **Install in Claude Desktop** — download `fantasy-mcp.mcpb` from the
   latest Release; double-click it (or Settings → Extensions → Install);
   fill in the form. First launch takes a minute while Desktop downloads
   Python and dependencies. Link to section 2.
2. **Get your ESPN cookies and league ID** — numbered steps for Chrome
   (DevTools → Application → Cookies → espn.com) and Safari (enable the
   Develop menu, then Web Inspector → Storage → Cookies), each with a
   screenshot in `docs/images/` showing where the panel is, which two rows to
   copy, and where `leagueId` sits in the URL. Note that cookies expire every
   few weeks: when a tool says "cookies", re-copy them into
   Settings → Extensions → ESPN Fantasy Football. Chrome screenshots are
   captured during implementation with cookie values redacted; Safari steps
   are text unless screenshots are supplied.
3. **Use with Claude Code / other clients** — existing snippet, unchanged.
4. **Tools** — unchanged.
5. **Develop and release** — `uv sync`, `uv run pytest`,
   `npx @anthropic-ai/mcpb pack . fantasy-mcp.mcpb` for a local build, and
   the tag steps from section 3.

## 5. Verification

- Existing test suite passes (runs in the workflow too).
- `npx @anthropic-ai/mcpb validate manifest.json` passes.
- `mcpb pack` output, listed with `unzip -l`, contains `manifest.json`,
  `pyproject.toml`, `uv.lock`, `src/fantasy_mcp/*.py`, and nothing from
  `tests/`, `docs/`, `.venv/`, `.git/`, `.env`.
- **Acceptance:** install the packed bundle in Claude Desktop on this Mac,
  fill in the form, and run `whoami` successfully. This is the only way to
  confirm that Desktop injects `user_config` into `env` for the experimental
  `uv` type. Fallback if it does not: pass the values as `args` instead and
  add a tiny argv parser in `main()`.
- Push a `v0.2.0` tag and confirm the Release carries `fantasy-mcp.mcpb`.
- **Result (2026-09-14, macOS Claude Desktop):** installed from an unsigned
  bundle; the `uv` runtime launched via the machine's existing
  `/opt/homebrew/bin/uv` (the no-uv-installed path is still unverified);
  `user_config` was injected via `env`; first `whoami` failed on the literal
  `${user_config.season}` placeholder, fixed in `config.py`; re-test with the rebuilt bundle passed — `whoami` and `get_matchup` returned live data with Season and Team ID blank.
