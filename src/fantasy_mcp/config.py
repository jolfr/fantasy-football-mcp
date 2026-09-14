"""Load ESPN settings from the environment (with .env fallback)."""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when required configuration is missing or malformed."""


@dataclass(frozen=True)
class Settings:
    espn_s2: str = field(repr=False)
    swid: str = field(repr=False)
    league_id: int
    season: int
    team_id: int | None


_REQUIRED = ("ESPN_S2", "ESPN_SWID", "ESPN_LEAGUE_ID")


def _env(name: str) -> str | None:
    """Return the variable's value, or None if unset, blank, or an unresolved ${...} template.

    Claude Desktop passes "${user_config.x}" through literally when the user leaves
    an optional extension field blank.
    """
    raw = os.environ.get(name, "").strip()
    if not raw or (raw.startswith("${") and raw.endswith("}")):
        return None
    return raw


def _int(name: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from e


def load_settings(load_dotenv_file: bool = True) -> Settings:
    if load_dotenv_file:
        load_dotenv()

    required = {k: v for k in _REQUIRED if (v := _env(k)) is not None}
    missing = [k for k in _REQUIRED if k not in required]
    if missing:
        raise ConfigError(
            "Missing required environment variables: " + ", ".join(missing)
            + ". Set them in the extension's settings in Claude Desktop, "
            "or, for a local checkout, copy .env.example to .env and fill them in."
        )

    season_raw = _env("ESPN_SEASON")
    team_raw = _env("ESPN_TEAM_ID")

    return Settings(
        espn_s2=required["ESPN_S2"],
        swid=required["ESPN_SWID"],
        league_id=_int("ESPN_LEAGUE_ID", required["ESPN_LEAGUE_ID"]),
        season=_int("ESPN_SEASON", season_raw) if season_raw else dt.date.today().year,
        team_id=_int("ESPN_TEAM_ID", team_raw) if team_raw else None,
    )
