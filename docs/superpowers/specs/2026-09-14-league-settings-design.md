# `get_league_settings` Tool — Design

**Date:** 2026-09-14
**Status:** Approved

## Goal

Expose the league's scoring rules, roster construction, schedule/playoff
format, waiver rules, and trade rules so Claude's start/sit, pickup, and
trade advice uses the league's actual scoring (e.g. PPR vs standard).

## Verified facts (2026-09-14, live)

- View `mSettings` returns `settings` with `name, size, isPublic,
  rosterSettings, scoringSettings, scheduleSettings, acquisitionSettings,
  tradeSettings, financeSettings, draftSettings` plus top-level `status`
  (`currentMatchupPeriod`, `finalScoringPeriod`) and `scoringPeriodId`.
- `rosterSettings.lineupSlotCounts`: `{lineupSlotId: count}` (zero counts
  present — drop them); `positionLimits`: `{positionId: limit}` with `-1` =
  unlimited; `moveLimit` `-1` = unlimited; `lineupLocktimeType` e.g.
  `INDIVIDUAL_GAME`.
- `scoringSettings.scoringType` e.g. `H2H_POINTS`; `scoringItems[]` of
  `{statId, points, pointsOverrides: {positionId: points}}` (46 items).
  D/ST items carry `points: 0` and the real value in `pointsOverrides["16"]`
  — effective points = `points` if non-zero else `pointsOverrides["16"]`
  if present. Scoring stat ids mostly match `stats.STAT_NAMES`; extras
  verified against live scoring: `198` = FG 50+ (raw `74`); points-allowed
  buckets `89` 0, `90` 1–6, `91` 7–13, `92` 14–17, `123` 28–34, `124`
  35–45, `125` 46+; yards-allowed buckets `128` <100, `129` 100–199,
  `130` 200–299 (Ravens: 251 yds → id 130 → +2, matches), `131` 300–349,
  `132` 350–399, `133` 400–449, `134` 450–499, `135` 500–549, `136` 550+.
  Ids `63, 201, 206, 209` remain unmapped — leave as `stat_<id>`.
- `scheduleSettings`: `matchupPeriodCount`, `matchupPeriodLength`,
  `playoffTeamCount`, `playoffSeedingRule`.
- `acquisitionSettings`: `acquisitionType`, `acquisitionBudget`,
  `minimumBid`, `waiverHours`, `waiverOrderReset`, `waiverProcessDays`.
- `tradeSettings`: `deadlineDate` (epoch ms), `revisionHours`,
  `vetoVotesRequired`.

## Changes

`stats.py`: add `SCORING_STAT_NAMES = {**STAT_NAMES, 198: "fg_made_50_plus",
<points/yards-allowed bucket names above, e.g. 89: "dst_points_allowed_0",
130: "dst_yards_allowed_200_299", 136: "dst_yards_allowed_550_plus">}` and
`scoring_name(stat_id) -> str` returning the name or `f"stat_{id}"`.

`shapes.py`: `shape_league_settings(league: dict) -> dict`:

```json
{
  "league_name": "...", "size": 12, "is_public": false,
  "scoring": {
    "type": "H2H_POINTS",
    "ppr": 1.0,                      // points for receptions (stat 53), 0.0 if absent
    "rules": {"pass_yds": 0.04, ...}, // effective non-zero points only (see override rule), name -> points (ints when integral)
    "summary": "Full PPR · 25 pass yds/pt · 10 rush/rec yds/pt · 4-pt pass TD · 6-pt rush/rec TD · -2 INT · -2 fumble lost"
  },
  "roster": {
    "lineup": {"QB": 1, ..., "BENCH": 7, "IR": 1},   // ids.LINEUP_SLOTS names, count > 0, in slot-id order
    "position_limits": {"QB": 4, ...},               // ids.POSITIONS names, limits >= 0 only
    "move_limit": null,                              // -1 -> null (unlimited)
    "lineup_lock": "INDIVIDUAL_GAME"
  },
  "schedule": {"regular_season_weeks": 14, "matchup_weeks_per_period": 1,
               "playoff_teams": 6, "playoff_seeding": "TOTAL_POINTS_SCORED",
               "current_week": 1, "final_week": 17},
  "waivers": {"type": "WAIVERS_TRADITIONAL", "budget": 100, "min_bid": 1,
              "waiver_hours": 24, "order_resets": true, "process_days": [...]},
  "trades": {"deadline": "2026-12-02", "review_hours": 24, "veto_votes_required": 5}
}
```

Summary rules (each part only when the stat exists and is non-zero):
- receptions: `1.0` → "Full PPR"; `0.5` → "Half PPR"; other non-zero →
  "{v} PPR"; absent/0 → "Standard (no PPR)".
- `pass_yds` → "{round(1/v)} pass yds/pt"; `rush_yds`/`rec_yds` → if equal
  "{n} rush/rec yds/pt" else separate.
- `pass_td` → "{v}-pt pass TD"; `rush_td`/`rec_td` → "{v}-pt rush/rec TD"
  if equal else separate.
- `pass_int` → "{v} INT"; `fumbles_lost` → "{v} fumble lost".
Joined by " · ". Numbers formatted without trailing `.0`.

`deadline`: `deadlineDate` ms → UTC date `YYYY-MM-DD`; null if absent/0.
All lookups tolerate missing keys (return nulls / empty dicts).

`server.py`: `get_league_settings()` → `client.get("mSettings")` →
`shape_league_settings(league)`. Standard error mapping. Docstring: when
to use (before scoring-dependent advice; to explain waivers/trades), field
meanings, that `rules` keys match `get_player` stat names and unmapped ids
appear as `stat_<id>`. `INSTRUCTIONS`: add "Call get_league_settings before
start/sit, pickup, or trade advice so recommendations use this league's
scoring (PPR or not) and roster limits." and list six tools.

## Testing

Fixture `tests/fixtures/league_settings.json` (trimmed real `mSettings`,
league name scrubbed; already on disk). Tests: `scoring_name` known/198/
unknown; `shape_league_settings` exact dict for the fixture (lineup order,
position limits without -1, ppr 1.0, summary string, deadline date,
process days); sparse league `{}` → nulls/empties, no exception; tool test
asserts view `["mSettings"]` and `league_name`; registration lists six
tools. Live check against the user's league.
