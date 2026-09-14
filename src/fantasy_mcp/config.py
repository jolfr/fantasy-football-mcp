"""Load ESPN settings: saved config file, then environment (with .env fallback)."""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from fantasy_mcp import settings_store


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


def _clean(raw: str | None) -> str | None:
    """None for unset, blank, or an unresolved ${...} template.

    Claude Desktop passes "${user_config.x}" through literally when the user leaves
    an optional extension field blank.
    """
    raw = (raw or "").strip()
    if not raw or (raw.startswith("${") and raw.endswith("}")):
        return None
    return raw


def _env(name: str) -> str | None:
    return _clean(os.environ.get(name))


def _int(name: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from e


def _value(name: str, saved: dict[str, str]) -> str | None:
    """Saved-file value first (the in-chat setup card writes it), then the environment."""
    return _clean(saved.get(name)) or _env(name)


def load_settings(load_dotenv_file: bool = True) -> Settings:
    if load_dotenv_file:
        load_dotenv()
    saved = settings_store.load()

    required = {k: v for k in _REQUIRED if (v := _value(k, saved)) is not None}
    missing = [k for k in _REQUIRED if k not in required]
    if missing:
        raise ConfigError(
            "ESPN league not configured (missing " + ", ".join(missing) + "). "
            "Call the setup tool to show the setup card, or set the values in the "
            "extension's settings in Claude Desktop, or, for a local checkout, "
            "copy .env.example to .env and fill them in."
        )

    season_raw = _value("ESPN_SEASON", saved)
    team_raw = _value("ESPN_TEAM_ID", saved)

    return Settings(
        espn_s2=required["ESPN_S2"],
        swid=required["ESPN_SWID"],
        league_id=_int("ESPN_LEAGUE_ID", required["ESPN_LEAGUE_ID"]),
        season=_int("ESPN_SEASON", season_raw) if season_raw else dt.date.today().year,
        team_id=_int("ESPN_TEAM_ID", team_raw) if team_raw else None,
    )
