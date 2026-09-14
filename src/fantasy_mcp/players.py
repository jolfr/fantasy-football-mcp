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


def is_id_like(value: Any) -> bool:
    """True for an int or a digit string (optionally negative, as D/ST ids are)."""
    return isinstance(value, int) or (isinstance(value, str) and value.strip().lstrip("-").isdigit())


def needs_index(inputs: list[Any]) -> bool:
    """True when any input must be resolved by name."""
    return any(not is_id_like(value) for value in inputs)


def resolve_players(
    inputs: list[str | int], index: list[dict[str, Any]]
) -> tuple[list[int], list[dict[str, Any]]]:
    """Resolve a mixed list of ids / names. Returns (ids in input order, unresolved entries)."""
    resolved: list[int] = []
    unresolved: list[dict[str, Any]] = []
    for raw in inputs:
        try:
            player_id = int(str(raw).strip()) if is_id_like(raw) else resolve_player(str(raw), index)
        except EspnError as e:
            unresolved.append({"input": raw, "error": str(e)})
            continue
        if player_id not in resolved:
            resolved.append(player_id)
    return resolved, unresolved
