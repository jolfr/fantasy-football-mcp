"""Prefab UI for player cards: pure functions from tool output to a PrefabApp."""

from __future__ import annotations

from typing import Any

from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Badge,
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    Column,
    DataTable,
    DataTableColumn,
    Metric,
    Muted,
    Row,
    Separator,
)
from prefab_ui.components.charts import ChartSeries, LineChart

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
_INJURY_VARIANT = {"ACTIVE": "success", "QUESTIONABLE": "warning", "DOUBTFUL": "warning"}
_STATUS_TEXT = {"FREEAGENT": "Free agent", "WAIVERS": "On waivers"}
_DASH = "—"


def _status_line(profile: dict[str, Any]) -> str:
    status = profile.get("league_status")
    if status == "ONTEAM":
        owner = (profile.get("owned_by") or {}).get("name")
        text = f"Rostered by {owner}" if owner else "Rostered"
    else:
        text = _STATUS_TEXT.get(status, str(status))
    last = profile.get("last_season") or {}
    if last.get("points") is not None:
        text += f" · {last.get('year')}: {last['points']} pts"
    return text


def _or_dash(value: Any) -> Any:
    return _DASH if value is None else value


def _owned_metric(ownership: dict[str, Any]) -> Metric:
    owned = ownership.get("percent_owned")
    change = ownership.get("percent_change")
    if owned is None:
        return Metric(label="Owned", value=_DASH)
    if change is None:
        return Metric(label="Owned", value=f"{owned}%")
    trend = "up" if change > 0 else "down" if change < 0 else "neutral"
    sentiment = {"up": "positive", "down": "negative", "neutral": "neutral"}[trend]
    return Metric(
        label="Owned",
        value=f"{owned}%",
        delta=f"{change:+.1f}%",
        trend=trend,
        trend_sentiment=sentiment,
    )


def _chart_rows(profile: dict[str, Any]) -> list[dict[str, Any]]:
    year = (profile.get("season") or {}).get("year")
    rows = [g for g in profile.get("game_log") or [] if g.get("season") == year]
    rows.sort(key=lambda g: g.get("week") or 0)
    return [{"week": f"W{g.get('week')}", "points": g.get("points"), "projected": g.get("projected")} for g in rows]


def _table_rows(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "season": g.get("season"),
            "week": g.get("week"),
            "points": _or_dash(g.get("points")),
            "projected": _or_dash(g.get("projected")),
            "line": stat_line(g.get("stats")),
        }
        for g in profile.get("game_log") or []
    ]


def player_card(profile: dict[str, Any]) -> PrefabApp:
    """Build the Prefab card for a ``get_player`` profile. Never raises on sparse input."""
    name = profile.get("name") or "Unknown player"
    position, team = profile.get("position"), profile.get("pro_team")
    season = profile.get("season") or {}
    ownership = profile.get("ownership") or {}
    injury = profile.get("injury_status")
    rank = season.get("positional_rank")
    chart_rows = _chart_rows(profile)
    table_rows = _table_rows(profile)

    with PrefabApp(title=f"{name} — {position} {team}") as app:
        with Card():
            with CardHeader():
                with Row(gap=2):
                    CardTitle(content=name)
                    Badge(label=f"{position} · {team}", variant="secondary")
                    if injury:
                        Badge(label=str(injury), variant=_INJURY_VARIANT.get(injury, "destructive"))
                CardDescription(content=_status_line(profile))
            with CardContent():
                with Column(gap=4):
                    with Row(gap=4):
                        Metric(label="Season pts", value=_or_dash(season.get("points")))
                        Metric(label="Projected", value=_or_dash(season.get("projected")), description="season")
                        Metric(label="Pos. rank", value=f"#{rank}" if rank is not None else _DASH)
                        _owned_metric(ownership)
                    if profile.get("outlook"):
                        Muted(content=profile["outlook"])
                    if chart_rows or table_rows:
                        Separator()
                    if chart_rows:
                        LineChart(
                            data=chart_rows,
                            series=[
                                ChartSeries(data_key="points", label="Points"),
                                ChartSeries(data_key="projected", label="Projected"),
                            ],
                            x_axis="week",
                            height=160,
                            show_dots=True,
                        )
                    if table_rows:
                        DataTable(
                            columns=[
                                DataTableColumn(key="season", header="Season", sortable=True),
                                DataTableColumn(key="week", header="Wk", sortable=True, align="right"),
                                DataTableColumn(key="points", header="Pts", sortable=True, align="right"),
                                DataTableColumn(key="projected", header="Proj", align="right"),
                                DataTableColumn(key="line", header="Line"),
                            ],
                            rows=table_rows,
                            search=False,
                            paginated=True,
                            page_size=10,
                        )
    return app
