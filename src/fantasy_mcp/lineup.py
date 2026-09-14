"""Exact optimal-lineup assignment for a fantasy roster (max-weight bipartite matching)."""

from __future__ import annotations

from typing import Any

NON_STARTING_SLOTS = {20, 21}  # BENCH, IR
IR_SLOT = 21
# Players who cannot play this week; ESPN may still publish a projection for them.
INACTIVE_STATUSES = {"OUT", "INJURY_RESERVE", "SUSPENSION"}
_KEEP_STARTER_BONUS = 1e-6  # tie-break: prefer leaving a current starter in their slot
_FORBIDDEN = 1e9  # cost of an ineligible pairing (finite so the algorithm always terminates)


def _projection(player: dict[str, Any]) -> float:
    value = player.get("projected")
    return float(value) if value is not None else 0.0


def _min_cost_assignment(cost: list[list[float]]) -> list[int]:
    """Hungarian algorithm (Kuhn–Munkres): column chosen for each row, minimizing total cost.

    ``cost`` is n rows × m columns with n <= m. O(n²·m).
    """
    n, m = len(cost), len(cost[0])
    inf = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)  # p[j] = row (1-based) matched to column j
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta, j1 = inf, 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j], way[j] = cur, j0
                if minv[j] < delta:
                    delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    assignment = [0] * n
    for j in range(1, m + 1):
        if p[j]:
            assignment[p[j] - 1] = j - 1
    return assignment


def optimal_lineup(
    players: list[dict[str, Any]], slot_counts: dict[int, int]
) -> dict[int, list[dict[str, Any]]]:
    """Assign players to starting slots to maximize total projection.

    Exact: a max-weight bipartite matching between slot instances and players
    (Hungarian algorithm, polynomial in roster size), so FLEX/superflex slots
    and dual-eligible players are handled correctly. Players on IR, or whose
    injury status says they cannot play, are never started. Ties keep current
    starters in place. Returns ``{slot_id: [player rows]}`` for starting slots
    only, each slot's rows ordered by projection; a slot with no eligible
    player (or only players with a null projection) is left short.
    """
    pool = [
        p
        for p in players
        if p.get("slot_id") != IR_SLOT and (p.get("injury_status") or "").upper() not in INACTIVE_STATUSES
    ]
    pool.sort(key=lambda p: p.get("player_id") or 0)
    starting = sorted(
        (int(s), int(n)) for s, n in slot_counts.items() if int(s) not in NON_STARTING_SLOTS and n
    )
    slots = [slot for slot, count in starting for _ in range(count)]
    result: dict[int, list[dict[str, Any]]] = {slot: [] for slot, _ in starting}
    if not slots or not pool:
        return result

    # Columns: real players, then one zero-weight "leave empty" dummy per slot instance.
    n, k = len(slots), len(pool)
    cost: list[list[float]] = []
    for slot in slots:
        row = []
        for player in pool:
            if slot in (player.get("eligible_slots") or []):
                bonus = _KEEP_STARTER_BONUS if player.get("slot_id") == slot else 0.0
                row.append(-(_projection(player) + bonus))
            else:
                row.append(_FORBIDDEN)
        row.extend([0.0] * n)
        cost.append(row)

    for i, col in enumerate(_min_cost_assignment(cost)):
        if col < k and cost[i][col] < 0:  # a real player with positive value (not a dummy column)
            result[slots[i]].append(pool[col])
    for rows in result.values():
        rows.sort(key=lambda p: (-_projection(p), p.get("player_id") or 0))
    return result
