from fantasy_mcp.cards import stat_line


def test_qb_line():
    stats = {"pass_att": 34, "pass_comp": 18, "pass_yds": 164, "pass_td": 2, "rush_att": 5, "rush_yds": 31}
    assert stat_line(stats) == "18/34 164 yds 2 TD · 5 car 31 yds"


def test_qb_line_with_int():
    assert stat_line({"pass_comp": 20, "pass_att": 30, "pass_yds": 250, "pass_int": 1}) == "20/30 250 yds 1 INT"


def test_rb_line():
    stats = {
        "rush_att": 19, "rush_yds": 98, "rush_td": 2,
        "receptions": 3, "rec_yds": 23, "targets": 4,
        "fumbles": 1, "fumbles_lost": 1,
    }
    assert stat_line(stats) == "19 car 98 yds 2 TD · 3 rec 23 yds (4 tgt) · 1 fum lost"


def test_wr_line():
    assert stat_line({"receptions": 10, "rec_yds": 182, "targets": 13}) == "10 rec 182 yds (13 tgt)"


def test_wr_line_with_td_no_targets():
    assert stat_line({"receptions": 4, "rec_yds": 60, "rec_td": 1}) == "4 rec 60 yds 1 TD"


def test_kicker_line():
    assert stat_line({"fg_made": 2, "fg_att": 2, "xp_made": 5, "xp_att": 5}) == "FG 2/2 XP 5/5"


def test_kicker_line_made_only():
    assert stat_line({"fg_made": 1, "xp_made": 3}) == "FG 1 XP 3"


def test_dst_line():
    stats = {"dst_sacks": 2, "dst_int": 1, "dst_fumble_rec": 1, "dst_points_allowed": 23, "dst_yards_allowed": 251}
    assert stat_line(stats) == "2 sk 1 int 1 fr 23 pts 251 yds allowed"


def test_dst_line_touchdown_and_block():
    assert stat_line({"dst_blocked_kicks": 1, "dst_int_return_td": 1, "dst_points_allowed": 0}) == "1 blk 1 TD 0 pts allowed"


def test_empty_and_unknown_only():
    assert stat_line({}) == ""
    assert stat_line({"games_played": 1, "team_win": 1}) == ""


def test_numbers_render_without_trailing_zero():
    assert stat_line({"rush_att": 5.0, "rush_yds": 31.0}) == "5 car 31 yds"
