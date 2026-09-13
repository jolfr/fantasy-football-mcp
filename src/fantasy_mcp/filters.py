"""Builders for ESPN's X-Fantasy-Filter request header."""

from __future__ import annotations

from typing import Any

# Fantasy position name -> lineupSlotId used by ESPN's filterSlotIds.
POSITION_SLOTS: dict[str, int] = {
    "QB": 0,
    "RB": 2,
    "WR": 4,
    "TE": 6,
    "K": 17,
    "D_ST": 16,
}
SORTS = ("owned", "projected")
MAX_LIMIT = 50

_AVAILABLE = {"value": ["FREEAGENT", "WAIVERS"]}


def free_agent_filter(
    *, season: int, position: str | None, limit: int, sort: str
) -> dict[str, Any]:
    """Filter for available players, optionally by position, sorted by ownership or projection."""
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT} (got {limit}).")
    if sort not in SORTS:
        raise ValueError(f"sort must be one of {', '.join(SORTS)} (got {sort!r}).")

    players: dict[str, Any] = {"filterStatus": _AVAILABLE, "limit": limit}

    if position is not None:
        slot = POSITION_SLOTS.get(position.upper())
        if slot is None:
            raise ValueError(
                f"position must be one of {', '.join(POSITION_SLOTS)} (got {position!r})."
            )
        players["filterSlotIds"] = {"value": [slot]}

    if sort == "projected":
        # ESPN stat id "10<season>" is the season-long projected total.
        players["sortAppliedStatTotal"] = {
            "sortPriority": 1,
            "sortAsc": False,
            "value": f"10{season}",
        }
    else:
        players["sortPercOwned"] = {"sortPriority": 1, "sortAsc": False}

    return {"players": players}
