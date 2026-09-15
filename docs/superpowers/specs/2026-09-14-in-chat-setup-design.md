# In-Chat Setup Card — Design

**Date:** 2026-09-14
**Status:** Approved
**Builds on:** `2026-09-14-mcpb-distribution-design.md`

## Goal

Let a Claude Desktop user connect their ESPN league without ever opening a
settings form: install the extension, say "set up my fantasy league", and
fill in a card in the chat that explains where the cookies are, has one
input box per value, and confirms the connection in place.

## Scope

In:
- `settings_store.py`: a per-user config file in the platform app-data dir
- `load_settings()` precedence: saved file → env vars → `.env`
- `setup` app tool rendering a Prefab form card; `save_settings` tool
- Any tool called while unconfigured returns the setup card
- Manifest: cookie/league fields become optional; description updated
- `INSTRUCTIONS` and README updated for the new flow
- Dependency: `platformdirs`

Out (later): Safari steps inside the card (README link instead); editing
Season/Team ID from the card; a "forget my cookies" tool; secret storage in
the OS keychain.

## Known trade-off

Values typed into the card travel through an MCP tool call. The host may
show or log tool arguments, so the cookies are less private than in the
Desktop settings form (`sensitive: true`, OS keychain). The README keeps
the settings form documented as the more private alternative. Accepted for
this project's audience.

## Verified facts (2026-09-14, prefab-ui 0.20.2, fastmcp 4.0.3)

- Prefab has `Form(on_submit=...)`, `Field`/`FieldTitle`/`FieldDescription`,
  `Input(name=..., input_type="password" | "number", required=...)`, and
  `CallTool(tool, arguments={"k": "{{ k }}"}, on_success=[SetState(...)])`
  where `$result` is the tool's return value.
- App tools already exist here: `get_player` returns
  `ToolResult(content=text, structured_content=PrefabApp)`.
- `server._get_client()` caches one `EspnClient` in a module global.

## 1. Storage and precedence

`src/fantasy_mcp/settings_store.py`:

```python
KEYS = ("ESPN_S2", "ESPN_SWID", "ESPN_LEAGUE_ID", "ESPN_SEASON", "ESPN_TEAM_ID")

def config_path() -> Path:          # platformdirs.user_config_dir("fantasy-mcp") / "config.json"
def load() -> dict[str, str]:       # {} if missing or unreadable JSON
def save(values: dict[str, str]) -> Path   # only KEYS, non-empty values; mkdir -p; write 0600
```

`config.load_settings()` reads each variable as: saved file value, else
`_env(name)`. `.env` loading is unchanged (it populates env). The file wins
so that a save from the card always takes effect even if the Desktop form was
filled earlier.

`manifest.json`: `espn_s2`, `swid`, `league_id` → `required: false`;
descriptions: "Optional — or just ask Claude to set up your league in chat."
`description` → "Read-only access to your ESPN fantasy football team,
matchup, free agents, players, and league scoring rules. Set up in chat."

## 2. Tools

- `setup() -> ToolResult` (`@mcp.tool(app=True)`): content text = "Setup
  card shown. Ask the user to fill it in. If this client can't display
  cards, they can put the values in `.env` (see README)." Structured content
  = `setup_card(current)` where `current` has only `league_id` (never
  cookies).
- `save_settings(espn_s2: str, swid: str, league_id: str) -> dict`: strip
  inputs; validate SWID has `{...}` braces; `settings_store.save(...)`; reset
  `_client`; call the `whoami` lookup. Returns `{"ok": True, "league_name",
  "team_name", "season"}` or `{"ok": False, "error": <existing auth/not-found
  wording>}`. Never raises for user-fixable problems, so the card can render
  the result. Values are saved before the network check so a retry after a
  typo keeps the good fields.
- Unconfigured calls: Desktop renders a card only for `app=True` tools, so
  other tools cannot return the card. `load_settings` raises `ConfigError`
  whose message names the `setup` tool; tools surface it as a `ToolError`,
  and `INSTRUCTIONS` tells Claude to call `setup`.
- After a successful `save_settings`, `_client` is set to `None` so the next
  call builds a client from the new settings.

## 3. Card (`cards.setup_card(current: dict) -> PrefabApp`)

1. Heading "Connect your ESPN league"; one line: ESPN has no public API, so
   Claude signs in with the two cookies your browser uses. Claude saves them
   in a config file on this computer and uses them only to sign in to ESPN.
2. "Find your cookies (Chrome, Edge, Brave)" — five numbered steps: open
   fantasy.espn.com logged in → right-click → Inspect → **Application** tab
   → **Storage → Cookies → https://fantasy.espn.com** → click `espn_s2`,
   copy its Value (leave "Show URL-decoded" unchecked); same for `SWID`.
   Link: "Using Safari? See the README."
3. `Form`: `Field` "espn_s2 cookie" → `Input(name="espn_s2", input_type="password", required=True)`;
   `Field` "SWID cookie" (hint: keep the curly braces) → password input;
   `Field` "League ID" (hint: the `leagueId=` number in your league's URL) →
   `Input(name="league_id", input_type="number", required=True, value=current league id if any)`.
4. Button "Save & test" → `CallTool("save_settings", arguments={"espn_s2": "{{ espn_s2 }}",
   "swid": "{{ swid }}", "league_id": "{{ league_id }}"}, on_success=SetState("result", "$result"))`.
   Below the form, a status area bound to `result`: green "Connected —
   {team_name} in {league_name} ({season})" when `ok`, red `error` text
   otherwise. Inputs stay editable.

## 4. Instructions and README

`INSTRUCTIONS` additions:
- "If a tool returns the setup card, or the user asks to set up, connect,
  or change their league or cookies, call `setup` and ask them to fill in
  the card. Don't ask them to paste cookies into the chat."
- Cookie-expiry paragraph: "call `setup`; the card explains where to copy
  fresh cookies. Clients that can't show cards: Desktop's extension settings
  or `.env`."

README:
- Install steps: download → open → accept unsigned warning → "Start a new
  chat and say **set up my fantasy league** — a card walks you through it."
- Cookie section stays (card links here for Safari). Add one line: the
  extension's settings form (Settings → Extensions → ESPN Fantasy Football)
  is an alternative that keeps cookies in your keychain; values saved from
  the card take precedence.
- "When cookies expire": say **update my ESPN cookies**.

## 5. Testing

- `tests/test_settings_store.py`: save/load round-trip in `tmp_path`
  (monkeypatch `config_path`); mode `0600` on POSIX; `load()` → `{}` for
  missing file and for corrupt JSON; `save` drops empty values and unknown
  keys.
- `tests/test_config.py`: file values override env; env still used when
  file lacks a key; existing tests unchanged.
- `tests/test_server.py`: `setup` returns a `ToolResult` whose structured
  content contains a `Form` with password inputs named `espn_s2`/`swid` and
  never contains the current cookie value; `get_my_team` while unconfigured
  raises a `ToolError` naming `setup`; `save_settings` success (respx-mocked league
  response) returns `ok: True` with names and writes the file; bad cookies
  (401) return `ok: False` with the cookie message and still write the file.
- `tests/test_manifest.py`: the three fields are `required: False`.
- Manual acceptance: reinstall bundle with an empty form → "set up my
  fantasy league" → fill card → "Connected" → `get_matchup` works.
- **Result (2026-09-15, macOS Claude Desktop):** installed with an empty
  settings form; "what's my matchup" → Claude called `setup`; the card
  rendered with instructions and three inputs; Save & test showed the green
  "Connected" line using `SetState("result", RESULT)` unchanged; `get_matchup`
  then returned live data. The README link in the card is shown but Desktop
  does not open it from inside the card (copyable; acceptable).
