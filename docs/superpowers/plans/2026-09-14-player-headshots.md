# Player Headshots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the ESPN headshot (or team logo for a D/ST) on the `get_player` card and expose `headshot_url` in the profile JSON.

**Architecture:** A pure `headshot_url()` helper in `shapes.py` builds the CDN URL; `shape_player_card` adds it to the profile; `cards.player_card` renders it as a Prefab `Image` in the header; `server.get_player` declares the CDN in the app's CSP.

**Tech Stack:** Python 3.12, fastmcp 4.0.3 (`fastmcp.apps.PrefabAppConfig/ResourceCSP`), prefab-ui 0.20.2.

**Spec:** `docs/superpowers/specs/2026-09-14-player-headshots-design.md`

---

### Task 1: `headshot_url` + profile field

**Files:** Modify `src/fantasy_mcp/shapes.py`, `tests/test_shapes.py`

- [ ] **Step 1: Append failing tests to `tests/test_shapes.py`**

```python
def test_headshot_url_for_player_and_dst():
    assert shapes.headshot_url(4242335, "RB", "IND") == (
        "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4242335.png&w=350&h=254"
    )
    assert shapes.headshot_url(-16033, "D/ST", "BAL") == "https://a.espncdn.com/i/teamlogos/nfl/500/bal.png"


def test_headshot_url_missing_cases():
    assert shapes.headshot_url(-1, "D/ST", "UNKNOWN_99") is None
    assert shapes.headshot_url(-1, "D/ST", "FA") is None
    assert shapes.headshot_url(None, "WR", "ARI") is None


def test_shape_player_card_includes_headshot_url(player_card_json):
    out = shapes.shape_player_card(player_card_json["players"][0], player_card_json)
    assert out["headshot_url"].endswith("/4242335.png&w=350&h=254")
    assert list(out)[:2] == ["player_id", "headshot_url"]
```

- [ ] **Step 2:** `uv run pytest tests/test_shapes.py -v -k headshot` → 3 FAIL (`AttributeError: ... 'headshot_url'` / KeyError).

- [ ] **Step 3: Implement in `src/fantasy_mcp/shapes.py`.** Add constants beside the other module constants:
```python
HEADSHOT_URL = (
    "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/{player_id}.png&w=350&h=254"
)
TEAM_LOGO_URL = "https://a.espncdn.com/i/teamlogos/nfl/500/{team}.png"
```
Add before `shape_player_card`:
```python
def headshot_url(player_id: int | None, position: str | None, pro_team: str | None) -> str | None:
    """ESPN CDN image for a player (headshot) or a D/ST (team logo); None if unknown."""
    if position == "D/ST":
        if pro_team and pro_team != "FA" and not pro_team.startswith("UNKNOWN_"):
            return TEAM_LOGO_URL.format(team=pro_team.lower())
        return None
    if player_id is None:
        return None
    return HEADSHOT_URL.format(player_id=player_id)
```
In `shape_player_card`, compute `player_id = entry.get("id", player.get("id"))`, `position = ids.name(ids.POSITIONS, ...)`, `pro_team = ids.name(ids.PRO_TEAMS, ...)` as locals (reuse them in the dict), and insert `"headshot_url": headshot_url(player_id, position, pro_team),` immediately after `"player_id": player_id,`.

- [ ] **Step 4:** `uv run pytest -q` → `124 passed`.
- [ ] **Step 5:** Commit `feat: add ESPN headshot/logo URL to player profile`.

---

### Task 2: Image in the card + CSP on the tool

**Files:** Modify `src/fantasy_mcp/cards.py`, `tests/test_cards.py`, `src/fantasy_mcp/server.py`

- [ ] **Step 1: Append failing tests to `tests/test_cards.py`**
```python
def test_player_card_shows_headshot(player_card_json):
    app = player_card(_profile(player_card_json))
    (img,) = _nodes(app, "Image")
    assert img["src"].endswith("/4242335.png&w=350&h=254")
    assert img["alt"] == "Card Back"
    assert img["width"] == "96px" and img["height"] == "70px"


def test_player_card_without_headshot_has_no_image(player_card_json):
    profile = _profile(player_card_json)
    profile["headshot_url"] = None
    assert _nodes(player_card(profile), "Image") == []
```
- [ ] **Step 2:** `uv run pytest tests/test_cards.py -v -k headshot` → 2 FAIL.
- [ ] **Step 3: Implement in `src/fantasy_mcp/cards.py`.** Add `Image` to the `prefab_ui.components` import list. Replace the `CardHeader` block in `player_card` with:
```python
            with CardHeader():
                with Row(gap=4):
                    if profile.get("headshot_url"):
                        Image(src=profile["headshot_url"], alt=name, width="96px", height="70px")
                    with Column(gap=1):
                        with Row(gap=2):
                            CardTitle(content=name)
                            Badge(label=f"{position} · {team}", variant="secondary")
                            if injury:
                                Badge(label=str(injury), variant=_INJURY_VARIANT.get(injury, "destructive"))
                        CardDescription(content=_status_line(profile))
```
- [ ] **Step 4: `src/fantasy_mcp/server.py`.** Add `from fastmcp.apps import PrefabAppConfig, ResourceCSP`; add `ESPN_CDN = "https://a.espncdn.com"` after `logger = ...`; change the decorator to `@mcp.tool(app=PrefabAppConfig(csp=ResourceCSP(resource_domains=[ESPN_CDN])))`; append to the docstring's last paragraph: ` headshot_url points at ESPN's CDN (team logo for a D/ST) and is not verified to exist.`
- [ ] **Step 5:** `uv run pytest -q` → `126 passed`; `uv run fantasy-mcp </dev/null 2>&1 | grep -E "Traceback|Error" || echo OK` → `OK`.
- [ ] **Step 6:** Commit `feat: show ESPN headshot on the player card`.

---

### Task 3: Live check (controller)

- [ ] Export the live Jonathan Taylor card and a D/ST card with `prefab export --bundled`, screenshot with headless Chrome, confirm the headshot and the logo load.
