"""Prefab UI for player cards: pure functions from tool output to a PrefabApp."""

from __future__ import annotations

from typing import Any

Stats = dict[str, int | float]


def _n(value: Any) -> str:
    """Render a stat number without a trailing .0."""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")  # no scientific notation, max 2 dp


def _passing(s: Stats) -> str | None:
    if not any(k in s for k in ("pass_comp", "pass_att", "pass_yds", "pass_td", "pass_int")):
        return None
    parts: list[str] = []
    if "pass_comp" in s and "pass_att" in s:
        parts.append(f"{_n(s['pass_comp'])}/{_n(s['pass_att'])}")
    elif "pass_att" in s:
        parts.append(f"{_n(s['pass_att'])} att")
    if "pass_yds" in s:
        parts.append(f"{_n(s['pass_yds'])} yds")
    if s.get("pass_td"):
        parts.append(f"{_n(s['pass_td'])} TD")
    if s.get("pass_int"):
        parts.append(f"{_n(s['pass_int'])} INT")
    return " ".join(parts) or None


def _rushing(s: Stats) -> str | None:
    if not any(k in s for k in ("rush_att", "rush_yds", "rush_td")):
        return None
    parts = []
    if "rush_att" in s:
        parts.append(f"{_n(s['rush_att'])} car")
    if "rush_yds" in s:
        parts.append(f"{_n(s['rush_yds'])} yds")
    if s.get("rush_td"):
        parts.append(f"{_n(s['rush_td'])} TD")
    return " ".join(parts) or None


def _receiving(s: Stats) -> str | None:
    if not any(k in s for k in ("receptions", "targets", "rec_yds", "rec_td")):
        return None
    parts = []
    if "receptions" in s:
        parts.append(f"{_n(s['receptions'])} rec")
    if "rec_yds" in s:
        parts.append(f"{_n(s['rec_yds'])} yds")
    if s.get("rec_td"):
        parts.append(f"{_n(s['rec_td'])} TD")
    if "targets" in s:
        parts.append(f"({_n(s['targets'])} tgt)")
    return " ".join(parts) or None


def _fumbles(s: Stats) -> str | None:
    return f"{_n(s['fumbles_lost'])} fum lost" if s.get("fumbles_lost") else None


def _pair(s: Stats, made: str, att: str, label: str) -> str | None:
    if made not in s and att not in s:
        return None
    if att in s:
        return f"{label} {_n(s.get(made, 0))}/{_n(s[att])}"
    return f"{label} {_n(s[made])}"


def _kicking(s: Stats) -> str | None:
    parts = [p for p in (_pair(s, "fg_made", "fg_att", "FG"), _pair(s, "xp_made", "xp_att", "XP")) if p]
    return " ".join(parts) or None


_DST_COUNTS = (
    ("dst_sacks", "sk"),
    ("dst_int", "int"),
    ("dst_fumble_rec", "fr"),
    ("dst_blocked_kicks", "blk"),
    ("dst_safeties", "saf"),
)
_DST_TDS = (
    "dst_blocked_kick_td",
    "dst_kick_return_td",
    "dst_punt_return_td",
    "dst_fumble_return_td",
    "dst_int_return_td",
)


def _defense(s: Stats) -> str | None:
    if not any(k.startswith("dst_") for k in s):
        return None
    parts = [f"{_n(s[k])} {label}" for k, label in _DST_COUNTS if s.get(k)]
    tds = sum(float(s.get(k, 0)) for k in _DST_TDS)
    if tds:
        parts.append(f"{_n(tds)} TD")
    if "dst_points_allowed" in s:
        parts.append(f"{_n(s['dst_points_allowed'])} pts")
    if "dst_yards_allowed" in s:
        parts.append(f"{_n(s['dst_yards_allowed'])} yds")
    if "dst_points_allowed" in s or "dst_yards_allowed" in s:
        parts.append("allowed")
    return " ".join(parts) or None


def stat_line(stats: Stats | None) -> str:
    """Compact box-score line for one game, e.g. ``19 car 98 yds 2 TD · 3 rec 23 yds (4 tgt)``."""
    s = stats or {}
    segments = (_passing(s), _rushing(s), _receiving(s), _fumbles(s), _kicking(s), _defense(s))
    return " · ".join(seg for seg in segments if seg)
