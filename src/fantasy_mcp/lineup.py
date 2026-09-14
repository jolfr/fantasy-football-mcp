"""Exact optimal-lineup assignment for a fantasy roster."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

NON_STARTING_SLOTS = {20, 21}  # BENCH, IR
IR_SLOT = 21
# Players who cannot play this week; ESPN may still publish a projection for them.
INACTIVE_STATUSES = {"OUT", "INJURY_RESERVE", "SUSPENSION"}
_KEEP_STARTER_BONUS = 1e-6  # tie-break: prefer leaving a current starter in their slot


def _projection(player: dict[str, Any]) -> float:
    value = player.get("projected")
    return float(value) if value is not None else 0.0


def optimal_lineup(
    players: list[dict[str, Any]], slot_counts: dict[int, int]
) -> dict[int, list[dict[str, Any]]]:
    """Assign players to starting slots to maximize total projection.

    Solves the assignment exactly (memoized search over slot instances and the
    set of players already used), so flex/superflex slots and dual-eligible
    players are handled correctly. Players on IR, or whose injury status says
    they cannot play, are never started. Ties keep current starters in place.
    Returns ``{slot_id: [player rows]}`` for starting slots only; a slot that
    cannot be filled gets fewer rows than its count.
    """
    pool = [
        p
        for p in players
        if p.get("slot_id") != IR_SLOT and (p.get("injury_status") or "").upper() not in INACTIVE_STATUSES
    ]
    pool.sort(key=lambda p: p.get("player_id") or 0)  # deterministic exploration order
    starting = sorted(
        (int(s), int(n)) for s, n in slot_counts.items() if int(s) not in NON_STARTING_SLOTS and n
    )
    slots = [slot for slot, count in starting for _ in range(count)]
    eligible = [
        [i for i, p in enumerate(pool) if slot in (p.get("eligible_slots") or [])] for slot in slots
    ]
    value = [_projection(p) for p in pool]
    keep = [[_KEEP_STARTER_BONUS if pool[i].get("slot_id") == slot else 0.0 for i in range(len(pool))] for slot in slots]

    @lru_cache(maxsize=None)
    def best(i: int, used: int) -> tuple[float, tuple[int | None, ...]]:
        if i == len(slots):
            return 0.0, ()
        total, assignment = best(i + 1, used)  # leave this slot empty
        total, assignment = total, (None, *assignment)
        for j in eligible[i]:
            if used & (1 << j):
                continue
            sub_total, sub_assignment = best(i + 1, used | (1 << j))
            candidate = sub_total + value[j] + keep[i][j]
            if candidate > total:
                total, assignment = candidate, (j, *sub_assignment)
        return total, assignment

    _, assignment = best(0, 0)
    result: dict[int, list[dict[str, Any]]] = {slot: [] for slot, _ in starting}
    for slot, j in zip(slots, assignment):
        if j is not None:
            result[slot].append(pool[j])
    return result
