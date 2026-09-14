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

    def get(
        self,
        *views: str,
        fantasy_filter: dict[str, Any] | None = None,
        scoring_period: int | None = None,
    ) -> dict[str, Any]:
        """GET the league endpoint with one or more ``view`` params.

        ``scoring_period`` selects which NFL week's per-player stats/projections
        ESPN includes (defaults to the current week).
        """
        headers = {"Accept": "application/json"}
        if fantasy_filter is not None:
            headers["X-Fantasy-Filter"] = json.dumps(fantasy_filter)
        params: list[tuple[str, str]] = [("view", v) for v in views]
        if scoring_period is not None:
            params.append(("scoringPeriodId", str(scoring_period)))
        s = self.settings
        data = self._request(
            self.league_url,
            params,
            headers,
            not_found=f"league {s.league_id}, season {s.season}. Check ESPN_LEAGUE_ID and ESPN_SEASON",
        )
        if not isinstance(data, dict):
            raise EspnError("Unexpected league response from ESPN (not an object).")
        return data

    def get_pro_schedules(self) -> dict[str, Any]:
        """NFL teams with bye weeks and per-week games (league-independent)."""
        url = f"{BASE}/seasons/{self.settings.season}"
        data = self._request(
            url,
            [("view", "proTeamSchedules_wl")],
            {"Accept": "application/json"},
            not_found=f"the season {self.settings.season} pro schedules. Check ESPN_SEASON",
        )
        if not isinstance(data, dict):
            raise EspnError("Unexpected pro schedules response from ESPN (not an object).")
        return data

    def get_players_index(self) -> list[dict[str, Any]]:
        """Active players for the season (league-independent); ~2.6k entries."""
        url = f"{BASE}/seasons/{self.settings.season}/players"
        headers = {
            "Accept": "application/json",
            "X-Fantasy-Filter": json.dumps({"filterActive": {"value": True}}),
        }
        data = self._request(
            url,
            [("scoringPeriodId", "0"), ("view", "players_wl")],
            headers,
            not_found=f"the season {self.settings.season} player index. Check ESPN_SEASON",
        )
        if not isinstance(data, list):
            raise EspnError("Unexpected players index response from ESPN (not a list).")
        return data

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

    def _request(
        self, url: str, params: list[tuple[str, str]], headers: dict[str, str], *, not_found: str
    ) -> Any:
        """GET ``url`` and parse; ``not_found`` describes what a 404 means for this endpoint."""
        try:
            response = httpx.get(
                url, params=params, cookies=self._cookies, headers=headers, timeout=TIMEOUT_SECONDS
            )
        except httpx.RequestError as e:
            raise EspnError(f"Could not reach ESPN: {type(e).__name__}") from e
        return self._parse(response, not_found=not_found)

    def _parse(self, response: httpx.Response, *, not_found: str) -> Any:
        status = response.status_code
        if status in (401, 403):
            raise EspnAuthError(
                f"ESPN returned {status}. Your espn_s2/SWID cookies are missing, "
                "invalid, or expired — refresh them from your browser."
            )
        if status == 404:
            raise EspnNotFoundError(f"ESPN returned 404 for {not_found}.")
        if status >= 400:
            raise EspnError(f"ESPN returned HTTP {status}: {response.text[:200]}")

        try:
            return response.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise EspnAuthError(
                "ESPN returned a non-JSON response (likely a login page). "
                "Your espn_s2/SWID cookies are probably expired."
            ) from e
