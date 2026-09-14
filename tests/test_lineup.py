from fantasy_mcp.lineup import optimal_lineup

SLOTS = {0: 1, 2: 2, 4: 2, 6: 1, 16: 1, 17: 1, 20: 7, 21: 1, 23: 1}


def _p(pid, proj, eligible, slot=20):
    return {"player_id": pid, "projected": proj, "eligible_slots": eligible, "slot_id": slot}


def test_fills_dedicated_then_flex_by_projection():
    players = [
        _p(1, 19.4, [0, 7, 20, 21], slot=0),
        _p(2, 17.7, [2, 3, 23, 7, 20, 21], slot=2),
        _p(3, 12.0, [2, 3, 23, 7, 20, 21]),          # bench RB
        _p(4, 15.3, [3, 4, 5, 23, 7, 20, 21], slot=4),
        _p(5, 14.7, [3, 4, 5, 23, 7, 20, 21], slot=4),
        _p(6, 10.0, [3, 4, 5, 23, 7, 20, 21]),        # bench WR
        _p(7, 9.9, [5, 6, 23, 7, 20, 21], slot=6),
        _p(8, 6.8, [16, 20, 21], slot=16),
        _p(9, 8.9, [17, 20, 21], slot=17),
    ]
    out = optimal_lineup(players, SLOTS)
    assert [p["player_id"] for p in out[0]] == [1]
    assert [p["player_id"] for p in out[2]] == [2, 3]        # second RB slot takes the bench RB
    assert [p["player_id"] for p in out[4]] == [4, 5]
    assert [p["player_id"] for p in out[23]] == [6]          # flex gets the best remaining
    assert set(out) == {0, 2, 4, 6, 16, 17, 23}               # no bench/IR keys


def test_ir_players_are_never_moved():
    players = [_p(1, 30.0, [2, 23, 20, 21], slot=21), _p(2, 5.0, [2, 23, 20, 21], slot=2)]
    out = optimal_lineup(players, {2: 1, 23: 1, 20: 1, 21: 1})
    assert [p["player_id"] for p in out[2]] == [2]
    assert out[23] == []


def test_tie_keeps_current_starter_and_none_projection_is_zero():
    players = [_p(1, 10.0, [4, 20], slot=20), _p(2, 10.0, [4, 20], slot=4), _p(3, None, [4, 20])]
    out = optimal_lineup(players, {4: 1, 20: 2})
    assert [p["player_id"] for p in out[4]] == [2]


def test_slot_count_exceeds_players():
    out = optimal_lineup([_p(1, 5.0, [4, 20])], {4: 2, 20: 1})
    assert [p["player_id"] for p in out[4]] == [1]


def test_superflex_takes_bench_qb_and_flex_takes_rb():
    # Greedy (fill OP before FLEX) would put RB2 at OP and leave FLEX empty: 44. Exact: 54.
    players = [
        _p(1, 20.0, [0, 7, 20, 21], slot=0),
        _p(2, 10.0, [0, 7, 20, 21]),            # bench QB
        _p(3, 12.0, [2, 3, 23, 7, 20, 21], slot=2),
        _p(4, 12.0, [2, 3, 23, 7, 20, 21]),     # bench RB
    ]
    out = optimal_lineup(players, {0: 1, 2: 1, 7: 1, 23: 1, 20: 2})
    assert [p["player_id"] for p in out[7]] == [2]
    assert [p["player_id"] for p in out[23]] == [4]


def test_dual_eligible_player_is_placed_where_total_is_highest():
    # RB/WR 15, RB 14, WR 5: greedy-by-slot gives 20; exact gives 29 (RB/WR at WR, RB at RB).
    players = [_p(1, 15.0, [2, 4, 20]), _p(2, 14.0, [2, 20]), _p(3, 5.0, [4, 20])]
    out = optimal_lineup(players, {2: 1, 4: 1, 20: 1})
    assert [p["player_id"] for p in out[2]] == [2]
    assert [p["player_id"] for p in out[4]] == [1]


def test_out_players_are_never_started_even_with_a_projection():
    players = [
        {**_p(1, 30.0, [2, 20]), "injury_status": "OUT"},
        {**_p(2, 4.0, [2, 20]), "injury_status": "ACTIVE"},
    ]
    out = optimal_lineup(players, {2: 1, 20: 1})
    assert [p["player_id"] for p in out[2]] == [2]


def test_full_roster_size_is_fast():
    import time

    players = [_p(i, float(20 - i), [3, 4, 5, 23, 7, 20, 21]) for i in range(18)]
    t0 = time.perf_counter()
    out = optimal_lineup(players, {0: 1, 2: 2, 4: 3, 6: 1, 7: 1, 23: 2, 16: 1, 17: 1, 20: 7})
    assert time.perf_counter() - t0 < 1.0
    assert sum(len(v) for v in out.values()) == 6  # 3 WR + OP + 2 FLEX; no QB/RB/TE/DST/K eligible


def _brute_force_total(players, slot_counts):
    """Reference: exhaustive search over slot instances (tiny inputs only)."""
    from fantasy_mcp.lineup import INACTIVE_STATUSES, IR_SLOT, NON_STARTING_SLOTS

    pool = [
        p for p in players
        if p.get("slot_id") != IR_SLOT and (p.get("injury_status") or "").upper() not in INACTIVE_STATUSES
    ]
    slots = [s for s, n in sorted(slot_counts.items()) if s not in NON_STARTING_SLOTS for _ in range(n)]

    def rec(i, used):
        if i == len(slots):
            return 0.0
        best = rec(i + 1, used)
        for j, p in enumerate(pool):
            if j in used or slots[i] not in p["eligible_slots"]:
                continue
            best = max(best, (p["projected"] or 0.0) + rec(i + 1, used | {j}))
        return best

    return rec(0, frozenset())


def test_matches_brute_force_on_random_rosters():
    import random

    rng = random.Random(7)
    slot_menu = [0, 2, 4, 6, 16, 17, 23, 7, 3, 5]
    for _ in range(150):
        n_players = rng.randint(1, 9)
        players = []
        for pid in range(1, n_players + 1):
            eligible = rng.sample(slot_menu, rng.randint(1, 4)) + [20, 21]
            players.append({
                "player_id": pid,
                "projected": rng.choice([None, 0.0, round(rng.uniform(0, 25), 2)]),
                "eligible_slots": eligible,
                "slot_id": rng.choice(eligible),
                "injury_status": rng.choice(["ACTIVE", "ACTIVE", "OUT", None]),
            })
        counts = {s: rng.randint(0, 2) for s in rng.sample(slot_menu, rng.randint(1, 5))}
        counts[20] = 5
        out = optimal_lineup(players, counts)
        total = sum(p["projected"] or 0.0 for rows in out.values() for p in rows)
        assert abs(total - _brute_force_total(players, counts)) < 1e-6, (players, counts, out)
        for slot, rows in out.items():
            assert len(rows) <= counts[slot]
            assert all(slot in p["eligible_slots"] for p in rows)
        used = [p["player_id"] for rows in out.values() for p in rows]
        assert len(used) == len(set(used))


def test_two_count_slot_rows_ordered_by_projection_and_second_instance_correct():
    players = [_p(1, 12.0, [2, 20]), _p(2, 17.7, [2, 20], slot=2), _p(3, 1.0, [2, 20])]
    out = optimal_lineup(players, {2: 2, 20: 1})
    assert [p["player_id"] for p in out[2]] == [2, 1]


def test_large_dynasty_roster_is_fast():
    import time

    players = [
        _p(i, float((i * 7) % 23), [0, 2, 3, 4, 5, 6, 7, 23, 25, 20, 21], slot=20) for i in range(1, 31)
    ]
    t0 = time.perf_counter()
    out = optimal_lineup(players, {0: 1, 2: 2, 4: 3, 6: 1, 7: 2, 23: 2, 25: 1, 3: 1, 5: 1, 20: 10})
    assert time.perf_counter() - t0 < 0.5
    assert sum(len(v) for v in out.values()) == 14
