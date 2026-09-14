"""ESPN stat id -> name mapping for player game logs."""

from __future__ import annotations

from typing import Any

# Ids confirmed against live appliedStats (points / league scoring) and
# community documentation of ESPN's fantasy stat ids. Unlisted ids are dropped.
STAT_NAMES: dict[int, str] = {
    # passing
    0: "pass_att",
    1: "pass_comp",
    3: "pass_yds",
    4: "pass_td",
    19: "pass_2pt",
    20: "pass_int",
    # rushing
    23: "rush_att",
    24: "rush_yds",
    25: "rush_td",
    26: "rush_2pt",
    # receiving
    58: "targets",
    53: "receptions",
    42: "rec_yds",
    43: "rec_td",
    44: "rec_2pt",
    # misc
    68: "fumbles",
    72: "fumbles_lost",
    # kicking
    74: "fg_made_50_plus",
    77: "fg_made_40_49",
    80: "fg_made_under_40",
    83: "fg_made",
    84: "fg_att",
    85: "fg_missed",
    86: "xp_made",
    87: "xp_att",
    88: "xp_missed",
    # defense / special teams
    95: "dst_int",
    96: "dst_fumble_rec",
    97: "dst_blocked_kicks",
    98: "dst_safeties",
    99: "dst_sacks",
    93: "dst_blocked_kick_td",
    101: "dst_kick_return_td",
    102: "dst_punt_return_td",
    103: "dst_fumble_return_td",
    104: "dst_int_return_td",
    120: "dst_points_allowed",
    127: "dst_yards_allowed",
    # team context
    155: "team_win",
    156: "team_loss",
    210: "games_played",
}


def shape_stat_line(raw: dict[str, Any] | None) -> dict[str, int | float]:
    """Map ESPN ``{stat_id: value}`` to ``{name: value}``; drop unmapped ids and zeros."""
    line: dict[str, int | float] = {}
    for key, value in (raw or {}).items():
        try:
            name = STAT_NAMES[int(key)]
            number = float(value)
        except (KeyError, TypeError, ValueError):
            continue
        if number == 0:
            continue
        line[name] = int(number) if number.is_integer() else number
    return line
