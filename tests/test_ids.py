from fantasy_mcp.ids import LINEUP_SLOTS, POSITIONS, PRO_TEAMS, name


def test_known_ids():
    assert name(POSITIONS, 1) == "QB"
    assert name(LINEUP_SLOTS, 20) == "BENCH"
    assert name(LINEUP_SLOTS, 23) == "FLEX"
    assert name(PRO_TEAMS, 2) == "BUF"


def test_unknown_id_falls_back():
    assert name(POSITIONS, 999) == "UNKNOWN_999"
