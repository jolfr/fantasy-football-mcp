# Player Headshots — Design

**Date:** 2026-09-14
**Status:** Approved
**Builds on:** `2026-09-13-player-card-tool-design.md`, `2026-09-13-player-card-ui-design.md`

## Goal

Show the player's ESPN headshot (or team logo for a D/ST) on the
`get_player` card, and expose the image URL in the JSON profile.

## Verified facts (2026-09-14)

- ESPN CDN, no auth: `https://a.espncdn.com/i/headshots/nfl/players/full/{player_id}.png`
  → 200 `image/png` (~250 KB) for real players; 404 (HTML) for unknown ids.
  Resized variant: `https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/{player_id}.png&w=350&h=254`
  (~100 KB). Team logos: `https://a.espncdn.com/i/teamlogos/nfl/500/{abbrev lower}.png` → 200.
- Prefab `Image(src: str, alt: str, width: str | None, height: str | None)`;
  width/height are CSS strings (`"96px"`), not ints (ints raise `ValidationError`).
- The MCP Apps sandbox blocks external resources unless declared:
  `@mcp.tool(app=PrefabAppConfig(csp=ResourceCSP(resource_domains=[...])))`
  (`from fastmcp.apps import PrefabAppConfig, ResourceCSP`). Registration
  with a config behaves like `app=True` (same `ui` meta + resource).
- D/ST entries in ESPN data have `position == "D/ST"`; their `pro_team`
  is the team abbreviation from `ids.PRO_TEAMS` (e.g. `BAL`).

## Changes

### `shapes.py`

```python
HEADSHOT_URL = "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/{player_id}.png&w=350&h=254"
TEAM_LOGO_URL = "https://a.espncdn.com/i/teamlogos/nfl/500/{team}.png"

def headshot_url(player_id: int | None, position: str | None, pro_team: str | None) -> str | None:
```
- `position == "D/ST"` and `pro_team` is a known abbreviation (not
  `UNKNOWN_*`, not `FA`) → `TEAM_LOGO_URL` with the abbreviation lower-cased
  (ESPN uses `wsh` for Washington — our table already says `WSH`).
- else `player_id` present → `HEADSHOT_URL`.
- else `None`.

`shape_player_card` adds `"headshot_url": headshot_url(player_id, position, pro_team)`
right after `player_id`. (Roster/free-agent rows do NOT get it — YAGNI until
those have cards.)

### `cards.py`

In `player_card`, the `CardHeader` becomes a `Row(gap=4)` with the image at
left and the existing title/badges/description in a `Column`:

```
CardHeader
└ Row(gap=4)
  ├ Image(src=headshot_url, alt=name, width="96px", height="70px")   # omitted if headshot_url is None
  └ Column(gap=1)
    ├ Row(gap=2): CardTitle, Badge(position·team), Badge(injury)
    └ CardDescription(status line)
```

### `server.py`

```python
from fastmcp.apps import PrefabAppConfig, ResourceCSP

ESPN_CDN = "https://a.espncdn.com"

@mcp.tool(app=PrefabAppConfig(csp=ResourceCSP(resource_domains=[ESPN_CDN])))
def get_player(...)
```
Docstring gains: "headshot_url points at ESPN's CDN (team logo for a D/ST);
it is not verified to exist." Nothing else changes.

## Errors

None new. A 404 headshot simply renders as a broken/blank 96×70 image;
acceptable for v1 (no fallback component in prefab-ui 0.20.2).

## Testing

`tests/test_shapes.py`: `headshot_url(4242335, "RB", "IND")` → combiner URL
with the id; `headshot_url(-16033, "D/ST", "BAL")` → `.../500/bal.png`;
`headshot_url(-1, "D/ST", "UNKNOWN_99")` → None; `headshot_url(None, "WR",
"ARI")` → None; `shape_player_card` fixture output has `headshot_url`
ending `/4242335.png&w=350&h=254`.

`tests/test_cards.py`: fixture card has exactly one `Image` node with that
`src`, `alt == "Card Back"`, `width == "96px"`; sparse profile (no
`headshot_url`) has no `Image`.

`tests/test_server.py`: existing `get_player` tests still pass; the
registration test additionally asserts the tool's UI meta is present (CSP
lives in the resource's meta, which the in-memory client does not expose
— do not assert on it).

Manual: `prefab export --bundled` + headless Chrome screenshot shows the
headshot; a D/ST card shows the logo.
