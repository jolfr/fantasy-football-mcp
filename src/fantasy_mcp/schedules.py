"""Opponent / bye / kickoff lookup from ESPN's pro team schedules."""

from __future__ import annotations

import datetime as dt
from typing import Any


def iso_utc(epoch_ms: Any) -> str | None:
    """UTC ISO-8601 timestamp (whole seconds) for an ESPN epoch-ms value, or None."""
    if not epoch_ms:
        return None
    return (
        dt.datetime.fromtimestamp(int(epoch_ms) / 1000, dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _teams(schedules: dict[str, Any]) -> dict[int, dict[str, Any]]:
    teams = (schedules.get("settings") or {}).get("proTeams") or []
    return {t["id"]: t for t in teams if isinstance(t, dict) and "id" in t}


def game_context(schedules: dict[str, Any], pro_team_id: int | None, week: int) -> dict[str, Any]:
    """``{"opponent": "@KC" | "vs BUF" | "BYE" | None, "kickoff": ISO-8601 UTC | None}``."""
    teams = _teams(schedules)
    team = teams.get(pro_team_id) if pro_team_id is not None else None
    if team is None:
        return {"opponent": None, "kickoff": None}
    games = (team.get("proGamesByScoringPeriod") or {}).get(str(week)) or []
    if team.get("byeWeek") == week or not games:
        return {"opponent": "BYE", "kickoff": None}
    game = games[0]
    home = game.get("homeProTeamId") == pro_team_id
    other_id = game.get("awayProTeamId") if home else game.get("homeProTeamId")
    other = (teams.get(other_id) or {}).get("abbrev") or "?"
    prefix = "vs " if home else "@"
    return {"opponent": f"{prefix}{other.upper()}", "kickoff": iso_utc(game.get("date"))}
