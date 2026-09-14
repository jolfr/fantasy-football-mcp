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


class FilterError(ValueError):
    """A tool argument could not be turned into a valid ESPN filter."""


def normalize_position(position: str) -> str:
    """Canonical position key: upper-case, with ``D/ST`` accepted as ``D_ST``."""
    return position.upper().replace("/", "_")


def free_agent_filter(
    *, season: int, position: str | None, limit: int, sort: str
) -> dict[str, Any]:
    """Filter for available players, optionally by position, sorted by ownership or projection."""
    if not 1 <= limit <= MAX_LIMIT:
        raise FilterError(f"limit must be between 1 and {MAX_LIMIT} (got {limit}).")
    if sort not in SORTS:
        raise FilterError(f"sort must be one of {', '.join(SORTS)} (got {sort!r}).")

    players: dict[str, Any] = {
        "filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
        "limit": limit,
    }

    if position is not None:
        slot = POSITION_SLOTS.get(normalize_position(position))
        if slot is None:
            raise FilterError(
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


WEEKS_IN_SEASON = 18


def player_card_filter(player_ids: int | list[int], *, season: int) -> dict[str, Any]:
    """Filter for player cards: season totals, last season, and weekly projections."""
    ids = [player_ids] if isinstance(player_ids, int) else list(player_ids)
    stat_ids = [f"00{season}", f"10{season}", f"00{season - 1}"]
    stat_ids += [f"11{season}{week}" for week in range(1, WEEKS_IN_SEASON + 1)]
    return {
        "players": {
            "filterIds": {"value": ids},
            "filterStatsForTopScoringPeriodIds": {"value": 17, "additionalValue": stat_ids},
        }
    }


def player_ids_filter(player_ids: list[int]) -> dict[str, Any]:
    """Filter restricting a player view to specific ESPN player ids."""
    return {"players": {"filterIds": {"value": list(player_ids)}}}
