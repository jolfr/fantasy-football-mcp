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
