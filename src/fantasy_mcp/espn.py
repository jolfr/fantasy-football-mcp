"""Minimal ESPN fantasy football v3 API client."""

from __future__ import annotations

import json
from typing import Any

import httpx

from fantasy_mcp.config import Settings

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
TIMEOUT_SECONDS = 15.0


class EspnError(Exception):
    """Base error for ESPN API failures."""


class EspnAuthError(EspnError):
    """Cookies missing, invalid, or expired."""


class EspnNotFoundError(EspnError):
    """League/season not found."""


class EspnClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.league_url = (
            f"{BASE}/seasons/{settings.season}/segments/0/leagues/{settings.league_id}"
        )
        self._cookies = {"espn_s2": settings.espn_s2, "SWID": settings.swid}

    def get(self, *views: str, fantasy_filter: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET the league endpoint with one or more ``view`` params."""
        headers = {"Accept": "application/json"}
        if fantasy_filter is not None:
            headers["X-Fantasy-Filter"] = json.dumps(fantasy_filter)

        try:
            response = httpx.get(
                self.league_url,
                params=[("view", v) for v in views],
                cookies=self._cookies,
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )
        except httpx.RequestError as e:
            raise EspnError(f"Could not reach ESPN: {type(e).__name__}") from e
        return self._parse(response)

    def find_my_team_id(self, league: dict[str, Any] | None = None) -> int:
        """Return the configured team id, or the team whose owners include our SWID.

        ``league`` may be passed to reuse an already-fetched ``mTeam`` payload.
        """
        if self.settings.team_id is not None:
            return self.settings.team_id

        if league is None:
            league = self.get("mTeam")

        swid = self.settings.swid.lower()
        for team in league.get("teams", []):
            owners = [o.lower() for o in team.get("owners", [])]
            if swid in owners:
                return int(team["id"])

        raise EspnError(
            f"No team in league {self.settings.league_id} is owned by the configured "
            "ESPN_SWID. Check ESPN_SWID or set ESPN_TEAM_ID explicitly."
        )

    def _parse(self, response: httpx.Response) -> dict[str, Any]:
        status = response.status_code
        if status in (401, 403):
            raise EspnAuthError(
                f"ESPN returned {status}. Your espn_s2/SWID cookies are missing, "
                "invalid, or expired — refresh them from your browser."
            )
        if status == 404:
            s = self.settings
            raise EspnNotFoundError(
                f"ESPN returned 404 for league {s.league_id}, season {s.season}. "
                "Check ESPN_LEAGUE_ID and ESPN_SEASON."
            )
        if status >= 400:
            raise EspnError(f"ESPN returned HTTP {status}: {response.text[:200]}")

        try:
            return response.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise EspnAuthError(
                "ESPN returned a non-JSON response (likely a login page). "
                "Your espn_s2/SWID cookies are probably expired."
            ) from e
