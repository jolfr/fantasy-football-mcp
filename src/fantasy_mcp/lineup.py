"""Greedy optimal-lineup assignment for a fantasy roster."""

from __future__ import annotations

from typing import Any

DEDICATED_SLOTS = (0, 2, 4, 6, 16, 17)  # QB, RB, WR, TE, D/ST, K
NON_STARTING_SLOTS = {20, 21}  # BENCH, IR
IR_SLOT = 21


def _projection(player: dict[str, Any]) -> float:
    value = player.get("projected")
    return float(value) if value is not None else 0.0


def _fill(slot_id: int, count: int, pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [p for p in pool if slot_id in (p.get("eligible_slots") or [])]
    eligible.sort(key=lambda p: (-_projection(p), p.get("slot_id") != slot_id, p.get("player_id") or 0))
    chosen = eligible[:count]
    for p in chosen:
        pool.remove(p)
    return chosen


def optimal_lineup(players: list[dict[str, Any]], slot_counts: dict[int, int]) -> dict[int, list[dict[str, Any]]]:
    """Assign players to starting slots to maximize total projection.

    Dedicated slots are filled first (they never compete with each other), then
    flex-type slots take the best remaining eligible players. Players on IR are
    never moved. Returns ``{slot_id: [player rows]}`` for starting slots only.
    """
    pool = [p for p in players if p.get("slot_id") != IR_SLOT]
    starting = {int(s): int(n) for s, n in slot_counts.items() if int(s) not in NON_STARTING_SLOTS and n}
    result: dict[int, list[dict[str, Any]]] = {}
    for slot_id in DEDICATED_SLOTS:
        if slot_id in starting:
            result[slot_id] = _fill(slot_id, starting[slot_id], pool)
    for slot_id in sorted(s for s in starting if s not in DEDICATED_SLOTS):
        result[slot_id] = _fill(slot_id, starting[slot_id], pool)
    return result
