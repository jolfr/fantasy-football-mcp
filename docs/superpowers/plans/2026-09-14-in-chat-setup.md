# In-Chat Setup Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Claude Desktop user connect their ESPN league from a card in the chat — instructions, one input per value, Save & test — with the values persisted in a per-user config file.

**Architecture:** A new `settings_store` module owns a JSON file in the platform config dir; `config.load_settings` reads it ahead of env vars. A `setup` app tool renders a Prefab `Form` (`cards.setup_card`) whose Save button calls a new `save_settings` tool, which writes the file, resets the cached ESPN client, and runs the `whoami` lookup so the card can show "Connected". Unconfigured tools raise a `ToolError` that names `setup`; `INSTRUCTIONS` tells Claude to call it. Manifest fields become optional so install needs no form.

**Tech Stack:** FastMCP 4 (`@mcp.tool(app=True)`, `ToolResult`), prefab-ui 0.20.2 (`Form`, `Field`, `Input`, `CallTool`, `SetState`, `If`), platformdirs, pytest + respx.

**Spec:** `docs/superpowers/specs/2026-09-14-in-chat-setup-design.md`

**Spec amendment (verified while planning):** Desktop renders a Prefab card only for tools registered with `app=True` (the host needs `_meta.ui.resourceUri`). So unconfigured non-app tools cannot "return the setup card"; instead they raise `ToolError("… call the setup tool …")` and Claude calls `setup`. Task 4 updates the spec text.

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `src/fantasy_mcp/settings_store.py` | create | Locate, load, save the per-user config JSON |
| `src/fantasy_mcp/config.py` | modify | Precedence: saved file → env → `.env`; friendlier missing-config message |
| `src/fantasy_mcp/cards.py` | modify | `setup_card(current)` — instructions + form |
| `src/fantasy_mcp/server.py` | modify | `setup` app tool, `save_settings` tool, `NOT_CONFIGURED` error, `INSTRUCTIONS` |
| `manifest.json` | modify | Cookie/league fields optional; description |
| `pyproject.toml` / `uv.lock` | modify | add `platformdirs` |
| `tests/conftest.py` | modify | autouse fixture isolating the config file in `tmp_path` |
| `tests/test_settings_store.py` | create | store round-trip, permissions, corrupt file |
| `tests/test_config.py` | modify | file-over-env precedence |
| `tests/test_cards.py` | modify | setup card structure |
| `tests/test_server.py` | modify | `setup`, `save_settings`, unconfigured error |
| `tests/test_manifest.py` | modify | optional fields |
| `README.md` | modify | new install flow |

---

### Task 1: `settings_store` module

**Files:**
- Create: `src/fantasy_mcp/settings_store.py`
- Modify: `pyproject.toml` (dependency), `tests/conftest.py`
- Test: `tests/test_settings_store.py`

- [ ] **Step 1: Add the dependency**

Run: `uv add platformdirs` — expected: `pyproject.toml` gains `"platformdirs>=4"` (whatever current major is) under `dependencies`, and `uv.lock` updates.

- [ ] **Step 2: Add an autouse fixture so no test ever touches the real config file**

Append to `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def isolated_config_path(tmp_path, monkeypatch):
    """Every test gets its own settings file; never read or write the developer's real one."""
    from fantasy_mcp import settings_store

    path = tmp_path / "fantasy-mcp" / "config.json"
    monkeypatch.setattr(settings_store, "config_path", lambda: path)
    return path
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_settings_store.py`:

```python
import json
import os
import stat
import sys

import pytest

from fantasy_mcp import settings_store


def test_load_missing_file_is_empty(isolated_config_path):
    assert not isolated_config_path.exists()
    assert settings_store.load() == {}


def test_save_then_load_round_trip(isolated_config_path):
    path = settings_store.save({"ESPN_S2": "abc", "ESPN_SWID": "{X}", "ESPN_LEAGUE_ID": "42"})
    assert path == isolated_config_path
    assert settings_store.load() == {"ESPN_S2": "abc", "ESPN_SWID": "{X}", "ESPN_LEAGUE_ID": "42"}


def test_save_drops_unknown_and_empty_values(isolated_config_path):
    settings_store.save({"ESPN_S2": "abc", "ESPN_SWID": "", "ESPN_TEAM_ID": None, "OTHER": "x"})
    assert settings_store.load() == {"ESPN_S2": "abc"}


def test_save_overwrites_previous_file(isolated_config_path):
    settings_store.save({"ESPN_S2": "old", "ESPN_LEAGUE_ID": "1"})
    settings_store.save({"ESPN_S2": "new"})
    assert settings_store.load() == {"ESPN_S2": "new"}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_save_sets_owner_only_permissions(isolated_config_path):
    settings_store.save({"ESPN_S2": "abc"})
    mode = stat.S_IMODE(os.stat(isolated_config_path).st_mode)
    assert mode == 0o600


def test_load_corrupt_file_is_empty(isolated_config_path):
    isolated_config_path.parent.mkdir(parents=True)
    isolated_config_path.write_text("{not json")
    assert settings_store.load() == {}


def test_load_ignores_non_string_and_unknown_entries(isolated_config_path):
    isolated_config_path.parent.mkdir(parents=True)
    isolated_config_path.write_text(json.dumps({"ESPN_S2": "abc", "ESPN_LEAGUE_ID": 42, "junk": "x"}))
    assert settings_store.load() == {"ESPN_S2": "abc", "ESPN_LEAGUE_ID": "42"}
```

- [ ] **Step 4: Run to verify they fail**

Run: `uv run pytest tests/test_settings_store.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'fantasy_mcp.settings_store'` (the conftest fixture imports it).

- [ ] **Step 5: Implement**

Create `src/fantasy_mcp/settings_store.py`:

```python
"""Per-user saved ESPN settings (written by the in-chat setup card).

Lives in the platform config directory, e.g.
``~/Library/Application Support/fantasy-mcp/config.json`` on macOS,
``%APPDATA%\\fantasy-mcp\\config.json`` on Windows, ``~/.config/fantasy-mcp/config.json``
on Linux. Values are the same ESPN_* keys the environment uses.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from platformdirs import user_config_dir

KEYS = ("ESPN_S2", "ESPN_SWID", "ESPN_LEAGUE_ID", "ESPN_SEASON", "ESPN_TEAM_ID")


def config_path() -> Path:
    return Path(user_config_dir("fantasy-mcp", appauthor=False)) / "config.json"


def load() -> dict[str, str]:
    """Saved values, or {} if the file is missing or unreadable."""
    try:
        raw = json.loads(config_path().read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: str(v) for k, v in raw.items() if k in KEYS and isinstance(v, (str, int))}


def save(values: dict[str, str | None]) -> Path:
    """Write the known, non-empty values (replacing the file) with owner-only permissions."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = {k: v for k, v in values.items() if k in KEYS and v}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(kept, f, indent=2)
    os.chmod(path, 0o600)
    return path
```

- [ ] **Step 6: Run to verify they pass**

Run: `uv run pytest tests/test_settings_store.py -v` — expected: 7 PASS. Then `uv run pytest -q` — expected: all pass (existing count + 7).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/fantasy_mcp/settings_store.py tests/conftest.py tests/test_settings_store.py
git commit -m "feat: add per-user settings store for in-chat setup"
```

---

### Task 2: Saved file takes precedence in `load_settings`

**Files:**
- Modify: `src/fantasy_mcp/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py` (it already has `_set(monkeypatch, **overrides)`, `REQUIRED`, `dt`, `pytest`, `ConfigError`, `load_settings`):

```python
def test_saved_file_overrides_env(monkeypatch):
    from fantasy_mcp import settings_store

    _set(monkeypatch, ESPN_LEAGUE_ID="1", ESPN_S2="env-s2")
    settings_store.save({"ESPN_S2": "file-s2", "ESPN_LEAGUE_ID": "99"})
    s = load_settings(load_dotenv_file=False)
    assert s.espn_s2 == "file-s2"
    assert s.league_id == 99
    assert s.swid == "{ABC-123}"  # not in the file, so env still supplies it


def test_saved_file_alone_is_enough(monkeypatch):
    from fantasy_mcp import settings_store

    _set(monkeypatch, ESPN_S2=None, ESPN_SWID=None, ESPN_LEAGUE_ID=None)
    settings_store.save({"ESPN_S2": "s2", "ESPN_SWID": "{X}", "ESPN_LEAGUE_ID": "7", "ESPN_TEAM_ID": "3"})
    s = load_settings(load_dotenv_file=False)
    assert (s.espn_s2, s.swid, s.league_id, s.team_id) == ("s2", "{X}", 7, 3)


def test_missing_config_message_names_setup(monkeypatch):
    _set(monkeypatch, ESPN_S2=None)
    with pytest.raises(ConfigError, match="setup"):
        load_settings(load_dotenv_file=False)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_config.py -v -k "saved_file or names_setup"` — expected: 3 FAIL (first two on values, third on the message).

- [ ] **Step 3: Implement**

In `src/fantasy_mcp/config.py`, add `from fantasy_mcp import settings_store` after the dotenv import, and replace `load_settings` with:

```python
def _value(name: str, saved: dict[str, str]) -> str | None:
    """Saved-file value first (the in-chat setup card writes it), then the environment."""
    raw = (saved.get(name) or "").strip()
    return raw or _env(name)


def load_settings(load_dotenv_file: bool = True) -> Settings:
    if load_dotenv_file:
        load_dotenv()
    saved = settings_store.load()

    required = {k: v for k in _REQUIRED if (v := _value(k, saved)) is not None}
    missing = [k for k in _REQUIRED if k not in required]
    if missing:
        raise ConfigError(
            "ESPN league not configured (missing " + ", ".join(missing) + "). "
            "Call the setup tool to show the setup card, or set the values in the "
            "extension's settings in Claude Desktop, or, for a local checkout, "
            "copy .env.example to .env and fill them in."
        )

    season_raw = _value("ESPN_SEASON", saved)
    team_raw = _value("ESPN_TEAM_ID", saved)

    return Settings(
        espn_s2=required["ESPN_S2"],
        swid=required["ESPN_SWID"],
        league_id=_int("ESPN_LEAGUE_ID", required["ESPN_LEAGUE_ID"]),
        season=_int("ESPN_SEASON", season_raw) if season_raw else dt.date.today().year,
        team_id=_int("ESPN_TEAM_ID", team_raw) if team_raw else None,
    )
```

Update the module docstring to: `"""Load ESPN settings: saved config file, then environment (with .env fallback)."""`

- [ ] **Step 4: Run the suite**

Run: `uv run pytest -q` — expected: all pass. `test_missing_required_lists_all` and `test_missing_required_points_at_desktop_and_env` still pass (they assert substrings that remain: variable names, "Claude Desktop", ".env").

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/config.py tests/test_config.py
git commit -m "feat: saved settings file takes precedence over env"
```

---

### Task 3: `setup_card` in `cards.py`

**Files:**
- Modify: `src/fantasy_mcp/cards.py`
- Test: `tests/test_cards.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cards.py` (it has `_nodes(app, node_type)` walking `app.to_json()["view"]`; add `setup_card` to the `from fantasy_mcp.cards import ...` line):

```python
def test_setup_card_has_password_inputs_and_calls_save_settings():
    app = setup_card({})
    inputs = {n["name"]: n for n in _nodes(app, "Input")}
    assert set(inputs) == {"espn_s2", "swid", "league_id"}
    assert inputs["espn_s2"]["inputType"] == "password"
    assert inputs["swid"]["inputType"] == "password"
    assert inputs["league_id"]["inputType"] == "number"
    assert all(n["required"] for n in inputs.values())

    (form,) = _nodes(app, "Form")
    submit = form["onSubmit"]
    submit = submit[0] if isinstance(submit, list) else submit
    assert submit["action"] == "toolCall"
    assert submit["tool"] == "save_settings"
    assert submit["arguments"] == {
        "espn_s2": "{{ espn_s2 }}",
        "swid": "{{ swid }}",
        "league_id": "{{ league_id }}",
    }


def test_setup_card_prefills_league_id_but_never_cookies():
    app = setup_card({"league_id": 588659244})
    inputs = {n["name"]: n for n in _nodes(app, "Input")}
    assert inputs["league_id"].get("value") == "588659244"
    assert "value" not in inputs["espn_s2"] or not inputs["espn_s2"]["value"]
    assert "value" not in inputs["swid"] or not inputs["swid"]["value"]


def test_setup_card_explains_where_cookies_are():
    app = setup_card({})
    text = " ".join(str(n.get("content", "")) for n in _nodes(app, "Text") + _nodes(app, "Muted"))
    for phrase in ("Inspect", "Application", "Cookies", "espn_s2", "SWID", "URL-decoded"):
        assert phrase in text
    (link,) = _nodes(app, "Link")
    assert "fantasy-football-mcp#get-your-espn-cookies-and-league-id" in link["href"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cards.py -k setup_card -v` — expected: `ImportError: cannot import name 'setup_card'`.

- [ ] **Step 3: Implement**

In `src/fantasy_mcp/cards.py`, extend the `prefab_ui.components` import to also bring in `Alert, AlertDescription, Button, Field, FieldDescription, FieldTitle, Form, Heading, If, Input, Link, Text`, add `from prefab_ui.actions.mcp import CallTool`, `from prefab_ui.actions.state import SetState`, `from prefab_ui.rx import RESULT`, and append:

```python
README_COOKIES = "https://github.com/jolfr/fantasy-football-mcp#get-your-espn-cookies-and-league-id"

_COOKIE_STEPS = (
    "Open fantasy.espn.com in Chrome (or Edge/Brave) and make sure you're logged in.",
    "Right-click the page and choose Inspect, then click the Application tab.",
    "In the left sidebar, under Storage, expand Cookies and click https://fantasy.espn.com.",
    "Click the espn_s2 row and copy its Value from the box below the table "
    "(leave \"Show URL-decoded\" unchecked). Paste it below.",
    "Do the same for the SWID row — keep the curly braces.",
)


def setup_card(current: dict[str, Any]) -> PrefabApp:
    """Build the in-chat setup form. ``current`` may carry ``league_id``; cookies are never pre-filled."""
    league_id = current.get("league_id")
    save = CallTool(
        "save_settings",
        arguments={"espn_s2": "{{ espn_s2 }}", "swid": "{{ swid }}", "league_id": "{{ league_id }}"},
        on_success=SetState("result", RESULT),
    )
    with PrefabApp(title="Connect your ESPN league", state={"result": {"ok": False, "error": ""}}) as app:
        with Card():
            with CardHeader():
                CardTitle(content="Connect your ESPN league")
                CardDescription(
                    content="ESPN has no public API, so Claude signs in with the two cookies your "
                    "browser uses. They stay on this computer and are only sent to ESPN."
                )
            with CardContent():
                with Column(gap=4):
                    Heading(content="Find your cookies", level=4)
                    with Column(gap=1):
                        for i, step in enumerate(_COOKIE_STEPS, 1):
                            Text(content=f"{i}. {step}")
                    with Row(gap=1):
                        Muted(content="Using Safari?")
                        Link(content="See the README.", href=README_COOKIES, target="_blank")
                    Separator()
                    with Form(on_submit=save):
                        with Field():
                            FieldTitle(content="espn_s2 cookie")
                            Input(name="espn_s2", input_type="password", required=True)
                        with Field():
                            FieldTitle(content="SWID cookie")
                            FieldDescription(content="Keep the curly braces, e.g. {1234ABCD-...}.")
                            Input(name="swid", input_type="password", required=True)
                        with Field():
                            FieldTitle(content="League ID")
                            FieldDescription(content="The leagueId= number in your league's URL on fantasy.espn.com.")
                            Input(
                                name="league_id",
                                input_type="number",
                                required=True,
                                value=str(league_id) if league_id is not None else None,
                            )
                        Button(label="Save & test", button_type="submit")
                    with If("result.ok"):
                        with Alert(variant="success"):
                            AlertDescription(
                                content="Connected — {{ result.team_name }} in {{ result.league_name }} ({{ result.season }})."
                            )
                    with If("result.error"):
                        with Alert(variant="destructive"):
                            AlertDescription(content="{{ result.error }}")
    return app
```

If any component name above doesn't exist in prefab-ui 0.20.2 (check with `uv run python -c "import prefab_ui.components as c; print(hasattr(c, 'FieldTitle'), hasattr(c, 'AlertDescription'))"`), use the nearest one listed by `dir(prefab_ui.components)` and note it in your report. If `Alert.variant` rejects `"success"`, use `"default"` for the connected alert.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_cards.py -k setup_card -v` — expected: 3 PASS. If the `onSubmit` key or the `arguments` shape differs from the assertions, print `app.to_json()["view"]` once, adjust the **test** to the real serialized key names only if the semantics match (a `toolCall` action targeting `save_settings` with three interpolated arguments) — do not weaken what is asserted.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_mcp/cards.py tests/test_cards.py
git commit -m "feat: setup card with cookie instructions and save form"
```

---

### Task 4: `setup` and `save_settings` tools; unconfigured error names `setup`

**Files:**
- Modify: `src/fantasy_mcp/server.py`
- Modify: `docs/superpowers/specs/2026-09-14-in-chat-setup-design.md` (section 2 amendment)
- Test: `tests/test_server.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server.py` (it imports `server`, `Client`, `httpx`, `respx`, `pytest`, `ToolError`, `LEAGUE_URL`; the `client` fixture installs an `EspnClient`; the autouse `isolated_config_path` fixture from Task 1 is available by name):

```python
async def test_setup_tool_returns_card_without_cookies(isolated_config_path):
    from fantasy_mcp import settings_store

    settings_store.save({"ESPN_S2": "secret-s2", "ESPN_SWID": "{SECRET}", "ESPN_LEAGUE_ID": "4242"})
    async with Client(server.mcp) as c:
        tool = next(t for t in await c.list_tools() if t.name == "setup")
        assert tool.meta["ui"]["resourceUri"].startswith("ui://prefab/")
        result = await c.call_tool("setup", {})
    assert "setup card" in result.content[0].text.lower()
    dumped = json.dumps(result.structured_content)
    assert "secret-s2" not in dumped and "{SECRET}" not in dumped
    assert '"4242"' in dumped  # league id is pre-filled


async def test_unconfigured_tool_points_at_setup(monkeypatch):
    for key in ("ESPN_S2", "ESPN_SWID", "ESPN_LEAGUE_ID"):
        monkeypatch.delenv(key, raising=False)
    server.set_client_for_tests(None)
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="setup"):
            await c.call_tool("get_my_team", {})


@respx.mock
async def test_save_settings_writes_file_and_verifies(league_json, isolated_config_path):
    server.set_client_for_tests(None)
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(200, json=league_json))
    async with Client(server.mcp) as c:
        result = await c.call_tool(
            "save_settings", {"espn_s2": " s2-cookie ", "swid": "{ABC-123}", "league_id": "4242"}
        )
    assert result.data == {"ok": True, "league_name": "Test League", "team_name": "My Squad", "season": 2026}
    saved = json.loads(isolated_config_path.read_text())
    assert saved == {"ESPN_S2": "s2-cookie", "ESPN_SWID": "{ABC-123}", "ESPN_LEAGUE_ID": "4242"}


@respx.mock
async def test_save_settings_reports_bad_cookies_but_keeps_values(isolated_config_path):
    server.set_client_for_tests(None)
    respx.get(LEAGUE_URL).mock(return_value=httpx.Response(401))
    async with Client(server.mcp) as c:
        result = await c.call_tool(
            "save_settings", {"espn_s2": "bad", "swid": "{ABC-123}", "league_id": "4242"}
        )
    assert result.data["ok"] is False
    assert "cookies" in result.data["error"]
    assert isolated_config_path.exists()


async def test_save_settings_rejects_swid_without_braces(isolated_config_path):
    async with Client(server.mcp) as c:
        result = await c.call_tool(
            "save_settings", {"espn_s2": "s2", "swid": "ABC-123", "league_id": "4242"}
        )
    assert result.data["ok"] is False
    assert "curly braces" in result.data["error"]
    assert not isolated_config_path.exists()


async def test_save_settings_rejects_non_numeric_league_id(isolated_config_path):
    async with Client(server.mcp) as c:
        result = await c.call_tool(
            "save_settings", {"espn_s2": "s2", "swid": "{ABC-123}", "league_id": "abc"}
        )
    assert result.data["ok"] is False
    assert "League ID" in result.data["error"]
```

Note: `test_save_settings_writes_file_and_verifies` needs `LEAGUE_URL`'s season (2026) to match `load_settings`' default `dt.date.today().year`; the fixture URL is already 2026 and today's date is in 2026. If the suite is run in a later year, this test should set `ESPN_SEASON=2026` via `monkeypatch.setenv` — add that line now so it doesn't rot: `monkeypatch.setenv("ESPN_SEASON", "2026")` (add `monkeypatch` to the test's parameters).

Also update the existing tool-count test (`test_six_tools_registered` or whatever it is currently named — find it with `grep -n "tools_registered" tests/test_server.py`) to include `"save_settings"` and `"setup"` in the sorted list and rename it to match the new count.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_server.py -v -k "setup or save_settings or unconfigured or tools_registered"`
Expected: FAIL — `setup`/`save_settings` unknown tools; `unconfigured` fails with the old message; tool-count list mismatch.

- [ ] **Step 3: Implement in `server.py`**

Imports: add `setup_card` to the `fantasy_mcp.cards` import; add `from fantasy_mcp import settings_store`; add `from fantasy_mcp.config import ConfigError, Settings, load_settings` (Settings is needed below).

Replace `_get_client` with a version that keeps the same behavior (nothing to change — `load_settings` already raises `ConfigError` with a message naming `setup` after Task 2). Add just below `set_client_for_tests`:

```python
def _reset_client() -> None:
    global _client
    _client = None
```

Add the two tools after `whoami`:

```python
@mcp.tool(app=True)
def setup() -> ToolResult:
    """Show the in-chat setup card for connecting the user's ESPN league.

    Call this when any tool reports the league is not configured, or when the
    user asks to set up, connect, or change their league or cookies. The card
    explains where to find the espn_s2 and SWID cookies, has one input per
    value, and saves + verifies them via save_settings. Ask the user to fill in
    the card; do not ask them to paste cookies into the chat. If this client
    cannot display cards, tell the user to set the values in the extension's
    settings in Claude Desktop or in .env for a local checkout (see README).
    """
    saved = settings_store.load()
    current = {"league_id": saved["ESPN_LEAGUE_ID"]} if saved.get("ESPN_LEAGUE_ID") else {}
    return ToolResult(
        content="Setup card shown. Ask the user to fill it in and press Save & test.",
        structured_content=setup_card(current),
    )


@mcp.tool
def save_settings(espn_s2: str, swid: str, league_id: str) -> dict[str, Any]:
    """Save ESPN credentials and league id, then verify them against ESPN.

    Normally called by the setup card's Save & test button; you may call it
    directly if the user pasted values into the chat. Returns {"ok": true,
    "league_name", "team_name", "season"} on success, or {"ok": false,
    "error": "..."} with a message to relay. Values are stored in a per-user
    config file that takes precedence over the extension's settings form.
    """
    espn_s2, swid, league_id = espn_s2.strip(), swid.strip(), league_id.strip()
    if not (swid.startswith("{") and swid.endswith("}")):
        return {"ok": False, "error": "SWID must include the curly braces, e.g. {1234ABCD-...}."}
    if not league_id.isdigit():
        return {"ok": False, "error": f"League ID must be a number, got {league_id!r}."}
    if not espn_s2:
        return {"ok": False, "error": "espn_s2 is empty."}
    settings_store.save({"ESPN_S2": espn_s2, "ESPN_SWID": swid, "ESPN_LEAGUE_ID": league_id})
    _reset_client()
    try:
        client = _get_client()
        league = client.get("mTeam", "mSettings")
        team_id = client.find_my_team_id(league)
        who = shape_whoami(league, team_id, client.settings)
    except (EspnError, ConfigError) as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "league_name": who.get("league_name"),
        "team_name": who.get("team_name"),
        "season": who.get("season"),
    }
```

Check `shape_whoami`'s keys with `grep -n "def shape_whoami" -A 12 src/fantasy_mcp/shapes.py` and use its actual key names for league/team/season.

No change is needed in the other tools: they already catch `ConfigError` and raise `ToolError(str(e))`, and the message now names `setup`.

- [ ] **Step 4: Update `INSTRUCTIONS`**

In the `INSTRUCTIONS` string, change the tool list sentence to end with "…get_free_agents, get_player, setup, and save_settings exist." and replace the final cookie paragraph with:

```
If a tool says the league is not configured, or the user asks to set up,
connect, or change their league or cookies, call setup and ask them to fill
in the card -- do not ask them to paste cookies into the chat. If a tool
fails with a message mentioning "cookies", the ESPN session cookies have
expired: call setup; the card explains where to copy fresh ones. Clients
that cannot show cards: the values go in the extension's settings in Claude
Desktop (Settings → Extensions → ESPN Fantasy Football) or the .env file for
a local checkout.
```

Existing tests `test_instructions_name_both_config_locations` and `test_instructions_name_the_extension_as_displayed` still pass (they check "Settings → Extensions", ".env", and the display name).

- [ ] **Step 5: Amend the spec**

In `docs/superpowers/specs/2026-09-14-in-chat-setup-design.md` section 2, replace the "Unconfigured calls: …" bullet with: "Unconfigured calls: Desktop renders a card only for `app=True` tools, so other tools cannot return the card. `load_settings` raises `ConfigError` whose message names the `setup` tool; tools surface it as a `ToolError`, and `INSTRUCTIONS` tells Claude to call `setup`." Remove the sentence "Tools that return `dict` today change their return annotation to `dict | ToolResult`." In section 5, change "`get_my_team` while unconfigured returns the same card" to "`get_my_team` while unconfigured raises a `ToolError` naming `setup`."

- [ ] **Step 6: Run the suite**

Run: `uv run pytest -q` — expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_mcp/server.py tests/test_server.py docs/superpowers/specs/2026-09-14-in-chat-setup-design.md
git commit -m "feat: setup and save_settings tools for in-chat league setup"
```

---

### Task 5: Manifest — optional fields, description

**Files:**
- Modify: `manifest.json`
- Test: `tests/test_manifest.py`

- [ ] **Step 1: Update the test**

In `tests/test_manifest.py`, replace `test_secrets_are_sensitive_and_required` with:

```python
def test_secrets_are_sensitive_and_all_fields_optional():
    uc = _manifest()["user_config"]
    for key in ("espn_s2", "swid"):
        assert uc[key]["sensitive"] is True
    assert all(uc[key]["required"] is False for key in uc)


def test_description_mentions_chat_setup():
    assert "chat" in _manifest()["description"].lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_manifest.py -v` — expected: the two new tests FAIL.

- [ ] **Step 3: Edit `manifest.json`**

- `description`: `"Read-only access to your ESPN fantasy football team, matchup, free agents, players, and league scoring rules. Set it up in chat: just ask Claude to connect your league."`
- `user_config.espn_s2.required`, `user_config.swid.required`, `user_config.league_id.required` → `false`.
- Prefix those three `description`s with `"Optional — or ask Claude to set up your league in chat. "`.

- [ ] **Step 4: Validate and test**

Run: `npx -y @anthropic-ai/mcpb@2.1.2 validate manifest.json` — expected: "Manifest schema validation passes!". Run: `uv run pytest -q` — expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add manifest.json tests/test_manifest.py
git commit -m "feat: make extension form fields optional; describe in-chat setup"
```

---

### Task 6: README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Edit the install section**

Replace steps 4–5 of "Install in Claude Desktop" with:

```markdown
4. Skip the settings form (leave it empty and click Save) — you'll do setup in chat.
5. Start a new chat and say **set up my fantasy league**. A card walks you
   through copying two cookies from your browser and your league ID, then
   tests the connection.
6. Ask "how's my fantasy team doing?"
```

- [ ] **Step 2: Add the alternative and precedence note**

At the end of "Get your ESPN cookies and league ID" (before "### When cookies expire"), add:

```markdown
### Prefer not to type cookies in chat?

Enter them in **Settings → Extensions → ESPN Fantasy Football** instead;
Claude Desktop keeps them in your keychain. Values saved from the chat card
take precedence over the settings form.
```

- [ ] **Step 3: Update "When cookies expire"**

Replace the paragraph body with: "ESPN cookies expire every few weeks. When they do, tools fail with a message mentioning \"cookies\". Say **update my ESPN cookies** and fill in the card again (or update the settings form if you used that)."

- [ ] **Step 4: Update the Claude Code section**

After the code block, add: "Values saved from the in-chat setup card (`~/Library/Application Support/fantasy-mcp/config.json` on macOS, `~/.config/fantasy-mcp/` on Linux, `%APPDATA%\fantasy-mcp\` on Windows) take precedence over `.env`."

- [ ] **Step 5: Tools list**

Add to the Tools list after `whoami`: "- `setup` — shows the in-chat setup card; `save_settings` stores and verifies what you enter."

- [ ] **Step 6: Check the anchor still exists and commit**

Run: `grep -c '^## Get your ESPN cookies and league ID$' README.md` — expected `1`.

```bash
git add README.md
git commit -m "docs: in-chat setup flow in README"
```

---

### Task 7: Acceptance in Claude Desktop, then release 0.3.0

**Files:**
- Modify: `pyproject.toml`, `manifest.json` (versions), `uv.lock`
- Modify: spec section 5 (result)

- [ ] **Step 1: Build and install**

Run: `npx -y @anthropic-ai/mcpb@2.1.2 pack . fantasy-mcp.mcpb`. In Claude Desktop: uninstall the existing ESPN Fantasy Football extension, then open the new bundle; leave the settings form empty. Also move any real saved file aside so the first-run path is exercised: `mv ~/Library/Application\ Support/fantasy-mcp/config.json{,.bak}` if it exists.

- [ ] **Step 2: Exercise the flow**

In a new chat: "what's my matchup this week?" — expected: Claude reports the league isn't configured and calls `setup`; the card renders with the instructions and three inputs. Fill them in, press **Save & test** — expected: the green "Connected — … in … (2026)" line appears in the card. Then "what's my matchup this week?" again — expected: live data.

If Save & test shows nothing: the `$result` shape from the host may be wrapped. Check `~/Library/Logs/Claude/mcp-server-ESPN Fantasy Football.log` for the `save_settings` result, then change `SetState("result", RESULT)` in `cards.setup_card` to `SetState("result", Rx("$result.structuredContent"))` (import `Rx` from `prefab_ui.rx`), rebuild, reinstall, retry. Record which form worked in the spec.

If the card doesn't render at all, confirm `setup` shows `ui.resourceUri` in `tools/list` in that log, and that the bundle's `pyproject.toml` still has `fastmcp[apps]`.

- [ ] **Step 3: Record and release**

Append to spec section 5: "- **Result (date):** …" with what happened (card rendered, `$result` form used, connected).

Bump `version` to `0.3.0` in `pyproject.toml` and `manifest.json`; `uv lock`; `uv run pytest -q`.

```bash
git add docs/superpowers/specs/2026-09-14-in-chat-setup-design.md pyproject.toml manifest.json uv.lock
git commit -m "chore: release 0.3.0"
```

Then merge to `main` (fast-forward or PR), `git tag v0.3.0 && git push origin main --tags`, and confirm with `gh run watch` / `gh release view v0.3.0` that `fantasy-mcp.mcpb` is attached. If the tag push doesn't trigger a run within a minute, `git push --delete origin v0.3.0 && git push origin v0.3.0`.
