# `get_standings` Tool — Design

**Date:** 2026-09-14
**Status:** Approved

## Goal

League standings: every team's rank, record, points, streak, ESPN's
projected finish, waiver priority, transaction activity, and playoff
clinch status, with the user's team flagged.

## Verified facts (2026-09-14, live)

- Views `mTeam`, `mStandings`, `mSettings` together return `teams[]` with
  `id, name, abbrev, owners[] (SWIDs), playoffSeed, record.overall {wins,
  losses, ties, pointsFor, pointsAgainst, streakType (WIN|LOSS|NONE),
  streakLength, gamesBack}, currentProjectedRank, waiverRank,
  playoffClinchType (NONE|…), transactionCounter {acquisitions, drops,
  trades, acquisitionBudgetSpent}`; `members[]` with `id (SWID),
  displayName, firstName?, lastName?`; `settings.scheduleSettings
  {playoffTeamCount, playoffSeedingRule}`; `status.currentMatchupPeriod`,
  `seasonId`.
- Records/points update when ESPN finalizes a week (Tuesday); mid-week
  they lag the live scoreboard (`get_matchup` covers live).
- League members' real names appear in `members[]`; fixtures must use
  placeholders.

## Changes

`shapes.py`:
```python
def shape_standings(league: dict, my_team_id: int | None) -> dict
```
Output:
```json
{"season": 2026, "week": 1, "playoff_teams": 6, "playoff_seeding": "TOTAL_POINTS_SCORED",
 "teams": [
   {"rank": 1, "team_id": 12, "name": "...", "abbrev": "...", "owner": "Alex Owner",
    "is_me": true,
    "record": {"wins": 2, "losses": 0, "ties": 0},
    "points_for": 231.5, "points_against": 190.2,   // rounded 2
    "streak": "W2",                                  // f"{W|L}{n}"; null when NONE/0
    "games_back": 0.0,
    "projected_rank": 3,                             // currentProjectedRank; 0 -> null
    "waiver_priority": 5,                            // waiverRank; 0 -> null
    "transactions": {"acquisitions": 1, "drops": 1, "trades": 0, "faab_spent": 12},
    "clinched": null}]}                              // playoffClinchType unless NONE
```
- `owner`: member matched by the team's first `owners[]` entry
  (case-insensitive SWID); `"First Last"` when both present, else
  `firstName` alone, else `displayName`, else null. Teams with no owners →
  null.
- Sort by `rank` (playoffSeed); teams with no seed (0/None) go last in
  record order (wins desc, points_for desc). `rank` then re-numbered 1..n
  so the list is always gapless.
- Tolerant of missing keys throughout; `{}` → `{"season": None, "week":
  None, "playoff_teams": None, "playoff_seeding": None, "teams": []}`.

`server.py`: `get_standings()` → `league = client.get("mTeam", "mStandings",
"mSettings")`, `my = client.find_my_team_id(league)` (if that raises
because no team matches, still return standings with `is_me` all false —
catch `EspnError` from `find_my_team_id` only), return
`shape_standings(league, my)`. Docstring: when to use (records, rankings,
playoff picture, waiver order, who's active on waivers/trades), note
records lag until ESPN finalizes the week. INSTRUCTIONS: add "Use
get_standings for records, rankings, the playoff picture, or waiver
order." and list eight tools. README bullet.

## Testing

Fixture `tests/fixtures/standings.json` (already on disk): 4 teams with
synthetic records, seeds 1–4 stored out of id order, streak WIN/LOSS,
one clinched team, owners covering all four name fallbacks (full name /
displayName only / first name only / no owner).

Tests: exact dict for the first row; ordering by seed; streak formatting
(`W2`, `L1`, null); owner fallbacks; clinched; `is_me` true only for 12;
unseeded teams sorted by record and ranks gapless; sparse `{}`; tool test
asserting views and `is_me`; `find_my_team_id` failure still returns
standings; eight tools registered.

Live: `get_standings()` lists all 12 Trivora teams with `is_me` on team 12.
