# Claude Desktop Distribution (.mcpb) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship fantasy-mcp as a one-click Claude Desktop extension (`fantasy-mcp.mcpb`) built by GitHub Actions on every `v*` tag, with a README a non-technical user can follow.

**Architecture:** The repo root is the bundle: a `manifest.json` (MCPB v0.4, `server.type = "uv"`) declares a `user_config` form whose values Desktop injects as the same env vars `config.py` already reads. A `.mcpbignore` keeps tests/docs/venv out. A tag-triggered workflow tests, validates, packs, and attaches the bundle to a GitHub Release. Server code changes are text-only.

**Tech Stack:** MCPB CLI `@anthropic-ai/mcpb` 2.1.2 (via `npx`), uv, GitHub Actions (`actions/checkout`, `actions/setup-node`, `astral-sh/setup-uv`, `gh`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-mcpb-distribution-design.md`

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `src/fantasy_mcp/server.py` | modify (`INSTRUCTIONS`, lines 44-46) | Tell Claude where a Desktop user re-enters cookies |
| `src/fantasy_mcp/config.py` | modify (line 43) | Same, in the missing-config error |
| `tests/test_config.py` | modify | Pin the new error wording |
| `tests/test_server.py` | modify | Pin the new instructions wording |
| `manifest.json` | create | MCPB manifest + `user_config` form |
| `.mcpbignore` | create | Exclude non-runtime files from the bundle |
| `.gitignore` | modify | Ignore built `*.mcpb` |
| `tests/test_manifest.py` | create | Guard: manifest version == pyproject version; env mapping complete |
| `.github/workflows/release.yml` | create | Tag → test → validate → pack → Release |
| `docs/images/*.png` | create | Cookie walkthrough screenshots |
| `README.md` | rewrite | Desktop-first setup, cookie walkthrough, dev/release |
| `pyproject.toml` | modify | Version bump to 0.2.0 at release time |

---

### Task 1: Point cookie guidance at Desktop settings

**Files:**
- Modify: `src/fantasy_mcp/server.py:44-46`
- Modify: `src/fantasy_mcp/config.py:43`
- Test: `tests/test_config.py`, `tests/test_server.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_missing_required_points_at_desktop_and_env(monkeypatch):
    _set(monkeypatch, ESPN_S2=None)
    with pytest.raises(ConfigError) as exc:
        load_settings(load_dotenv_file=False)
    msg = str(exc.value)
    assert "Claude Desktop" in msg
    assert ".env" in msg
```

Append to `tests/test_server.py` (add `from fantasy_mcp.server import INSTRUCTIONS` next to the existing server imports at the top of the file if it is not already imported):

```python
def test_instructions_name_both_config_locations():
    assert "Settings → Extensions" in INSTRUCTIONS
    assert ".env" in INSTRUCTIONS
    assert "server's .env file" not in INSTRUCTIONS
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_config.py::test_missing_required_points_at_desktop_and_env tests/test_server.py::test_instructions_name_both_config_locations -v`
Expected: both FAIL on the `"Claude Desktop" in msg` / `"Settings → Extensions" in INSTRUCTIONS` assertions.

- [ ] **Step 3: Edit the two messages**

In `src/fantasy_mcp/config.py`, replace lines 41-44:

```python
        raise ConfigError(
            "Missing required environment variables: " + ", ".join(missing)
            + ". Set them in the extension's settings in Claude Desktop, "
            "or copy .env.example to .env and fill them in."
        )
```

In `src/fantasy_mcp/server.py`, replace the last paragraph of `INSTRUCTIONS` (lines 44-46):

```python
If a tool fails with a message mentioning "cookies", the user's ESPN session
cookies have expired: tell them to re-copy espn_s2 and SWID from their browser
into wherever the server is configured: the extension's settings in Claude
Desktop (Settings → Extensions → ESPN Fantasy Football), or the .env file for
a local checkout.
"""
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass, including the two new tests and the existing `test_missing_required_lists_all`.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/config.py src/fantasy_mcp/server.py tests/test_config.py tests/test_server.py
git commit -m "docs: point cookie guidance at Claude Desktop extension settings"
```

---

### Task 2: Manifest, ignore file, and version guard test

**Files:**
- Create: `manifest.json`
- Create: `.mcpbignore`
- Modify: `.gitignore`
- Create: `tests/test_manifest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_manifest.py`:

```python
"""Keep manifest.json in step with pyproject.toml and config.py."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _manifest() -> dict:
    return json.loads((ROOT / "manifest.json").read_text())


def test_manifest_version_matches_pyproject():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert _manifest()["version"] == pyproject["project"]["version"]


def test_manifest_uses_uv_runtime():
    server = _manifest()["server"]
    assert server["type"] == "uv"
    assert server["mcp_config"]["args"] == ["run", "--directory", "${__dirname}", "fantasy-mcp"]


def test_every_user_config_field_maps_to_an_env_var():
    m = _manifest()
    env = m["server"]["mcp_config"]["env"]
    expected = {
        "ESPN_S2": "${user_config.espn_s2}",
        "ESPN_SWID": "${user_config.swid}",
        "ESPN_LEAGUE_ID": "${user_config.league_id}",
        "ESPN_SEASON": "${user_config.season}",
        "ESPN_TEAM_ID": "${user_config.team_id}",
    }
    assert env == expected
    assert set(m["user_config"]) == {"espn_s2", "swid", "league_id", "season", "team_id"}


def test_secrets_are_sensitive_and_required():
    uc = _manifest()["user_config"]
    for key in ("espn_s2", "swid"):
        assert uc[key]["sensitive"] is True
        assert uc[key]["required"] is True
    assert uc["league_id"]["required"] is True
    assert uc["season"]["required"] is False
    assert uc["team_id"]["required"] is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: 4 FAIL with `FileNotFoundError: manifest.json`.

- [ ] **Step 3: Create `manifest.json`**

```json
{
  "manifest_version": "0.4",
  "name": "fantasy-mcp",
  "display_name": "ESPN Fantasy Football",
  "version": "0.1.0",
  "description": "Read-only access to your ESPN fantasy football team, matchup, free agents, and players.",
  "author": {
    "name": "Thomas Jack Carroll"
  },
  "repository": {
    "type": "git",
    "url": "https://github.com/jolfr/fantasy-football-mcp"
  },
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
    "espn_s2": {
      "type": "string",
      "title": "espn_s2 cookie",
      "description": "From your browser's cookies for espn.com while logged in to ESPN. See README: Get your ESPN cookies.",
      "sensitive": true,
      "required": true
    },
    "swid": {
      "type": "string",
      "title": "SWID cookie",
      "description": "Same place as espn_s2. Keep the curly braces.",
      "sensitive": true,
      "required": true
    },
    "league_id": {
      "type": "number",
      "title": "League ID",
      "description": "The leagueId=... number in your league's URL on fantasy.espn.com.",
      "required": true
    },
    "season": {
      "type": "number",
      "title": "Season (optional)",
      "description": "Defaults to the current calendar year. Set it during Jan-Jul to keep looking at last season.",
      "required": false
    },
    "team_id": {
      "type": "number",
      "title": "Team ID (optional)",
      "description": "Leave blank to auto-detect your team from your SWID.",
      "required": false
    }
  },
  "compatibility": {
    "platforms": ["darwin", "win32", "linux"],
    "runtimes": {
      "python": ">=3.12"
    }
  },
  "keywords": ["espn", "fantasy", "football", "nfl"]
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Validate with the MCPB CLI**

Run: `npx -y @anthropic-ai/mcpb@2.1.2 validate manifest.json`
Expected: output ends with a line saying the manifest is valid (e.g. `✓ Manifest is valid`). If it reports a schema error, fix the manifest — do not loosen the tests.

- [ ] **Step 6: Create `.mcpbignore` and ignore build output**

Create `.mcpbignore`:

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

Append to `.gitignore`:

```
# MCPB build output
*.mcpb
```

- [ ] **Step 7: Pack and inspect the bundle**

Run:
```bash
npx -y @anthropic-ai/mcpb@2.1.2 pack . fantasy-mcp.mcpb
unzip -l fantasy-mcp.mcpb
```
Expected: the listing contains `manifest.json`, `pyproject.toml`, `uv.lock`, `README.md`, `LICENSE`, `src/fantasy_mcp/*.py`; it does **not** contain any path starting with `tests/`, `docs/`, `.venv/`, `.git/`, or a file named `.env`. Total size well under 1 MB.

If `tests/` or `.venv/` appear, the ignore file is not being honored — check that `.mcpbignore` is at the repo root and has no trailing spaces.

- [ ] **Step 8: Commit**

```bash
git add manifest.json .mcpbignore .gitignore tests/test_manifest.py
git commit -m "feat: add MCPB manifest for Claude Desktop (uv runtime)"
```

---

### Task 3: Release workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create the workflow**

```yaml
name: Release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Check tag matches pyproject.toml and manifest.json
        run: |
          TAG="${GITHUB_REF_NAME#v}"
          PY=$(python3 -c 'import tomllib;print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')
          MF=$(python3 -c 'import json;print(json.load(open("manifest.json"))["version"])')
          echo "tag=$TAG pyproject=$PY manifest=$MF"
          if [ "$TAG" != "$PY" ] || [ "$TAG" != "$MF" ]; then
            echo "::error::Version mismatch: tag $TAG, pyproject $PY, manifest $MF"
            exit 1
          fi

      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.12"

      - name: Test
        run: |
          uv sync --locked
          uv run pytest -q

      - uses: actions/setup-node@v4
        with:
          node-version: lts/*

      - name: Validate and pack
        run: |
          npx -y @anthropic-ai/mcpb@2.1.2 validate manifest.json
          npx -y @anthropic-ai/mcpb@2.1.2 pack . fantasy-mcp.mcpb
          unzip -l fantasy-mcp.mcpb
          if unzip -l fantasy-mcp.mcpb | grep -E ' (tests|docs|\.venv|\.git|\.worktrees)/| \.env$'; then
            echo "::error::Bundle contains files that should be excluded (see matches above)"
            exit 1
          fi

      - name: Create GitHub Release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release create "$GITHUB_REF_NAME" fantasy-mcp.mcpb \
            --title "$GITHUB_REF_NAME" --generate-notes
```

- [ ] **Step 2: Lint the YAML locally**

Run: `uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/release.yml')); print('ok')"` — if `yaml` is not installed, run `uvx --from pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml')); print('ok')"`.
Expected: `ok`.

- [ ] **Step 3: Dry-run the version guard locally**

Run:
```bash
GITHUB_REF_NAME=v0.1.0 bash -c '
TAG="${GITHUB_REF_NAME#v}"
PY=$(python3 -c "import tomllib;print(tomllib.load(open(\"pyproject.toml\",\"rb\"))[\"project\"][\"version\"])")
MF=$(python3 -c "import json;print(json.load(open(\"manifest.json\"))[\"version\"])")
echo "tag=$TAG pyproject=$PY manifest=$MF"
[ "$TAG" = "$PY" ] && [ "$TAG" = "$MF" ] && echo MATCH || echo MISMATCH'
```
Expected: `tag=0.1.0 pyproject=0.1.0 manifest=0.1.0` then `MATCH`. (Use `uv run python3` if the system `python3` is older than 3.11 and lacks `tomllib`.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: build and attach .mcpb to GitHub Releases on tag"
```

---

### Task 4: Cookie walkthrough screenshots

**Files:**
- Create: `docs/images/chrome-cookies.png`
- Create: `docs/images/league-id.png`

These require a browser logged in to ESPN. Capture with the Chrome browser-automation tools if available in the session; otherwise the user captures them by hand following the same steps.

- [ ] **Step 1: Capture the Chrome cookies panel**

1. In Chrome, open `https://fantasy.espn.com/football/` while logged in.
2. Open DevTools (`Cmd+Option+I` on macOS, `F12` on Windows) → **Application** tab → left sidebar **Storage → Cookies → `https://fantasy.espn.com`**.
3. Type `s` in the cookies filter box so `espn_s2` and `SWID` rows are near the top.
4. Screenshot the DevTools pane at ~1200 px wide showing the sidebar path and both rows.
5. Redact the **Value** column of both rows (solid rectangle) before saving. Save as `docs/images/chrome-cookies.png`.

- [ ] **Step 2: Capture the league ID in the URL**

1. Navigate to your league's home page (`https://fantasy.espn.com/football/league?leagueId=...`).
2. Screenshot just the address bar with `leagueId=` visible; crop to ~900×80 px.
3. Save as `docs/images/league-id.png`.

- [ ] **Step 3: Check sizes and commit**

Run: `ls -la docs/images/ && file docs/images/*.png`
Expected: two PNGs, each under 500 KB.

```bash
git add docs/images/chrome-cookies.png docs/images/league-id.png
git commit -m "docs: add cookie walkthrough screenshots"
```

---

### Task 5: README rewrite

**Files:**
- Rewrite: `README.md`

- [ ] **Step 1: Replace `README.md` with the following**

````markdown
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
  server reports it can't find your team.

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
````

- [ ] **Step 2: Check links and images resolve**

Run: `grep -o 'docs/images/[a-z-]*\.png' README.md | sort -u | xargs ls -la`
Expected: both image files listed, no "No such file" errors.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: Desktop-first README with cookie walkthrough"
```

---

### Task 6: End-to-end acceptance in Claude Desktop

**Files:** none (manual verification; possible follow-up edit to `manifest.json`)

- [ ] **Step 1: Build a fresh bundle**

Run: `npx -y @anthropic-ai/mcpb@2.1.2 pack . fantasy-mcp.mcpb`

- [ ] **Step 2: Install it**

Open `fantasy-mcp.mcpb` with Claude Desktop (double-click). Accept the unsigned-extension prompt. In the form, enter the `espn_s2`, `SWID`, and league ID from this repo's `.env`. Leave Season and Team ID blank. Enable the extension.

- [ ] **Step 3: Verify the server works**

In a new Claude Desktop chat, ask: "Run whoami from the fantasy extension." Expected: the tool returns your league name, season, and team name.

If the tool fails with the "Missing required environment variables" message, Desktop did not inject `user_config` into `env` for the `uv` type. Fallback: check Desktop's MCP log (**Settings → Developer → Open Logs Folder**, file `mcp-server-fantasy-mcp.log`) for the exact command it ran, then open a follow-up: pass values as `args` per the spec's section 5 fallback. Do not proceed to Task 7 until `whoami` succeeds.

- [ ] **Step 4: Verify blank optionals are tolerated**

Still in Desktop, ask "what's my matchup this week?" Expected: `get_matchup` returns data for the current season — confirming a blank `season` field did not become an unparseable `ESPN_SEASON` value. If it fails with `ESPN_SEASON must be an integer`, Desktop passed an empty string; `config.py` already treats empty as unset via `os.environ.get(...)` truthiness, so this indicates a non-empty placeholder — read the log to see the value and adjust `config.py`'s `season_raw`/`team_raw` handling to `.strip()` before use.

- [ ] **Step 5: Record the result**

Append to the spec's section 5 in `docs/superpowers/specs/2026-09-14-mcpb-distribution-design.md`:

```markdown
- **Result (2026-09-14):** installed on macOS Claude Desktop <version>; `user_config` injected via `env`; `whoami` and `get_matchup` succeeded with blank optionals.
```

```bash
git add docs/superpowers/specs/2026-09-14-mcpb-distribution-design.md
git commit -m "docs: record .mcpb acceptance test result"
```

---

### Task 7: Cut v0.2.0

**Files:**
- Modify: `pyproject.toml` (version)
- Modify: `manifest.json` (version)

- [ ] **Step 1: Bump both versions**

In `pyproject.toml`: `version = "0.2.0"`.
In `manifest.json`: `"version": "0.2.0"`.

- [ ] **Step 2: Confirm the guard test passes and the lockfile is current**

Run: `uv lock && uv run pytest -q`
Expected: all pass (`uv lock` rewrites the project's own version entry in `uv.lock`; include that change in the commit).

- [ ] **Step 3: Commit, merge to main, tag, push**

```bash
git add pyproject.toml manifest.json uv.lock
git commit -m "chore: release 0.2.0"
git checkout main && git merge --ff-only feat/player-card-ui
git tag v0.2.0
git push origin main --tags
```

(If the branch cannot fast-forward, open a PR for it first and tag after merge — the tag must point at a commit on `main` that contains the workflow.)

- [ ] **Step 4: Watch the workflow and verify the release**

Run: `gh run watch --exit-status` then `gh release view v0.2.0`
Expected: workflow succeeds; the release lists `fantasy-mcp.mcpb` as an asset. Download it and confirm `unzip -l` shows `manifest.json` with `"version": "0.2.0"`:

```bash
gh release download v0.2.0 -p fantasy-mcp.mcpb -O /tmp/release.mcpb
unzip -p /tmp/release.mcpb manifest.json | grep '"version"'
```
