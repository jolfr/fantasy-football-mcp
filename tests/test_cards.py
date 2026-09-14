from fantasy_mcp.cards import player_card, stat_line
from fantasy_mcp.shapes import shape_player_card


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


def test_attempts_without_completions_still_render():
    assert stat_line({"pass_att": 5, "pass_yds": 40}) == "5 att 40 yds"


def test_large_and_fractional_numbers_never_use_scientific_notation():
    assert stat_line({"dst_yards_allowed": 1234567}) == "1234567 yds allowed"
    assert stat_line({"rush_yds": 123456.5}) == "123456.5 yds"
    assert stat_line({"rush_yds": 3.14159}) == "3.14 yds"


def _nodes(app, node_type):
    def walk(node):
        yield node
        for child in node.get("children") or []:
            yield from walk(child)

    return [n for n in walk(app.to_json()["view"]) if n.get("type") == node_type]


def _profile(player_card_json):
    return shape_player_card(player_card_json["players"][0], player_card_json)


def test_player_card_header_and_metrics(player_card_json):
    app = player_card(_profile(player_card_json))
    assert app.title == "Card Back — RB IND"

    assert [n["content"] for n in _nodes(app, "CardTitle")] == ["Card Back"]
    badges = {n["label"]: n["variant"] for n in _nodes(app, "Badge")}
    assert badges == {"RB · IND": "secondary", "ACTIVE": "success"}
    assert [n["content"] for n in _nodes(app, "CardDescription")] == [
        "Rostered by My Matchup Team · 2025: 362.3 pts"
    ]

    metrics = {n["label"]: n for n in _nodes(app, "Metric")}
    assert metrics["Season pts"]["value"] == 25.1
    assert metrics["Projected"]["value"] == 315.58
    assert metrics["Pos. rank"]["value"] == "#4"
    assert metrics["Owned"]["value"] == "99.9%"
    assert metrics["Owned"]["delta"] == "+0.0%"
    assert metrics["Owned"]["trend"] == "neutral"

    assert [n["content"] for n in _nodes(app, "Muted")] == [
        "Placeholder outlook: workhorse back with elite volume."
    ]


def test_player_card_chart_and_table(player_card_json):
    profile = _profile(player_card_json)
    profile["game_log"].insert(0, {"season": 2026, "week": 2, "points": 12.0, "projected": None, "stats": {}})
    app = player_card(profile)

    (chart,) = _nodes(app, "LineChart")
    assert chart["xAxis"] == "week"
    assert chart["data"] == [
        {"week": "W1", "points": 25.1, "projected": 17.75},
        {"week": "W2", "points": 12.0, "projected": None},
    ]
    assert [s["dataKey"] for s in chart["series"]] == ["points", "projected"]

    (table,) = _nodes(app, "DataTable")
    assert [c["key"] for c in table["columns"]] == ["season", "week", "points", "projected", "line"]
    assert table["paginated"] is True and table["pageSize"] == 10
    assert [(r["season"], r["week"]) for r in table["rows"]] == [(2026, 2), (2026, 1), (2025, 18), (2025, 17)]
    assert table["rows"][1]["line"] == "19 car 98 yds 2 TD · 3 rec 23 yds (4 tgt) · 1 fum lost"
    assert table["rows"][1]["projected"] == 17.75
    assert table["rows"][0]["projected"] == "—"


def test_player_card_hides_chart_with_a_single_game(player_card_json):
    app = player_card(_profile(player_card_json))  # fixture has one 2026 game
    assert _nodes(app, "LineChart") == []
    assert len(_nodes(app, "DataTable")) == 1


def test_player_card_sparse_profile_does_not_raise():
    profile = {
        "player_id": 1,
        "name": "Rookie",
        "position": "WR",
        "pro_team": "ARI",
        "injury_status": None,
        "injured": None,
        "eligible_slots": [],
        "league_status": "FREEAGENT",
        "owned_by": None,
        "ownership": {"percent_owned": None, "percent_started": None, "percent_change": None, "adp": None},
        "season": {"year": 2026, "projected": None, "points": None, "positional_rank": None},
        "last_season": None,
        "outlook": None,
        "game_log": [],
    }
    app = player_card(profile)
    assert app.title == "Rookie — WR ARI"
    assert [n["label"] for n in _nodes(app, "Badge")] == ["WR · ARI"]
    assert [n["content"] for n in _nodes(app, "CardDescription")] == ["Free agent"]
    assert {n["label"]: n["value"] for n in _nodes(app, "Metric")} == {
        "Season pts": "—",
        "Projected": "—",
        "Pos. rank": "—",
        "Owned": "—",
    }
    assert "delta" not in {n["label"]: n for n in _nodes(app, "Metric")}["Owned"]
    assert _nodes(app, "Muted") == []
    assert _nodes(app, "LineChart") == []
    assert _nodes(app, "DataTable") == []


def test_player_card_status_and_injury_variants(player_card_json):
    profile = _profile(player_card_json)
    profile["league_status"] = "WAIVERS"
    profile["owned_by"] = None
    profile["injury_status"] = "OUT"
    profile["ownership"]["percent_change"] = -1.25
    app = player_card(profile)
    assert [n["content"] for n in _nodes(app, "CardDescription")] == ["On waivers · 2025: 362.3 pts"]
    assert {n["label"]: n["variant"] for n in _nodes(app, "Badge")}["OUT"] == "destructive"
    owned = {n["label"]: n for n in _nodes(app, "Metric")}["Owned"]
    assert owned["delta"] == "-1.2%"
    assert owned["trend"] == "down" and owned["trendSentiment"] == "negative"

    profile["injury_status"] = "QUESTIONABLE"
    profile["league_status"] = "ONTEAM"
    app = player_card(profile)
    assert {n["label"]: n["variant"] for n in _nodes(app, "Badge")}["QUESTIONABLE"] == "warning"
    assert [n["content"] for n in _nodes(app, "CardDescription")] == ["Rostered · 2025: 362.3 pts"]


def test_player_card_separator_only_when_game_log_present(player_card_json):
    assert len(_nodes(player_card(_profile(player_card_json)), "Separator")) == 1
    empty = _profile(player_card_json)
    empty["game_log"] = []
    assert _nodes(player_card(empty), "Separator") == []


def test_player_card_empty_profile_does_not_raise():
    app = player_card({})
    assert app.title == "Unknown player — None None"
    assert [n["content"] for n in _nodes(app, "CardDescription")] == ["Status unknown"]
    assert _nodes(app, "DataTable") == []
