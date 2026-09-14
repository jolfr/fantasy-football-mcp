from fantasy_mcp.stats import STAT_NAMES, shape_stat_line


def test_maps_known_ids_drops_unknown_and_zero():
    raw = {"23": 19.0, "24": 98.0, "25": 2.0, "41": 3.0, "999": 7.0, "72": 0.0}
    assert shape_stat_line(raw) == {"rush_att": 19, "rush_yds": 98, "rush_td": 2}


def test_integral_floats_become_ints_but_fractions_stay():
    assert shape_stat_line({"3": 163.0, "21": 53.13}) == {"pass_yds": 163}
    assert shape_stat_line({"24": 5.5}) == {"rush_yds": 5.5}


def test_none_and_empty():
    assert shape_stat_line(None) == {}
    assert shape_stat_line({}) == {}


def test_names_are_unique_snake_case():
    names = list(STAT_NAMES.values())
    assert len(names) == len(set(names))
    assert all(n == n.lower() and " " not in n for n in names)
