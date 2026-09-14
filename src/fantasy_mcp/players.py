"""Resolve player names against ESPN's active-player index."""

from __future__ import annotations

import re
from typing import Any

from fantasy_mcp import ids
from fantasy_mcp.espn import EspnError

MAX_CANDIDATES = 8
_DROP = re.compile(r"[.'’]")
_SPACES = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _SPACES.sub(" ", _DROP.sub("", text)).strip().casefold()


def _describe(player: dict[str, Any]) -> str:
    pos = ids.name(ids.POSITIONS, player.get("defaultPositionId", -1))
    team = ids.name(ids.PRO_TEAMS, player.get("proTeamId", -1))
    return f"{player.get('fullName') or '?'} ({pos}, {team}, id {player.get('id')})"


def _owned(player: dict[str, Any]) -> float:
    return float((player.get("ownership") or {}).get("percentOwned") or 0.0)


def resolve_player(name: str, index: list[dict[str, Any]]) -> int:
    """Return the ESPN player id for ``name``; raise EspnError if none or several match."""
    query = _norm(name)
    if not query:
        raise EspnError("A player name is required (got an empty name).")

    normed = [(_norm(p.get("fullName") or ""), p) for p in index]
    exact = [p for n, p in normed if n == query]
    if len(exact) == 1:
        return int(exact[0]["id"])

    matches = exact or [p for n, p in normed if query in n]
    if len(matches) == 1:
        return int(matches[0]["id"])
    if not matches:
        raise EspnError(f"No active player matches {name!r}.")

    top = sorted(matches, key=_owned, reverse=True)[:MAX_CANDIDATES]
    listed = "; ".join(_describe(p) for p in top)
    more = f" (+{len(matches) - len(top)} more)" if len(matches) > len(top) else ""
    raise EspnError(
        f"{name!r} matches {len(matches)} players (most-owned first){more}: {listed}. "
        "Retry with player_id or a fuller name."
    )
