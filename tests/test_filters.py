import pytest

from fantasy_mcp.filters import (
    MAX_LIMIT,
    FilterError,
    POSITION_SLOTS,
    SORTS,
    free_agent_filter,
    normalize_position,
)

STATUS = {"value": ["FREEAGENT", "WAIVERS"]}


def test_default_filter_sorts_by_percent_owned_with_no_position():
    out = free_agent_filter(season=2026, position=None, limit=10, sort="owned")
    assert out == {
        "players": {
            "filterStatus": STATUS,
            "limit": 10,
            "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
        }
    }


def test_position_is_case_insensitive_and_maps_to_slot():
    out = free_agent_filter(season=2026, position="rb", limit=5, sort="owned")
    assert out["players"]["filterSlotIds"] == {"value": [2]}
    assert out["players"]["limit"] == 5


def test_defense_position_maps_to_slot_16():
    out = free_agent_filter(season=2026, position="D_ST", limit=5, sort="owned")
    assert out["players"]["filterSlotIds"] == {"value": [16]}


def test_defense_accepts_slash_spelling_from_other_tools():
    out = free_agent_filter(season=2026, position="d/st", limit=5, sort="owned")
    assert out["players"]["filterSlotIds"] == {"value": [16]}


def test_projected_sort_uses_season_stat_id():
    out = free_agent_filter(season=2026, position=None, limit=10, sort="projected")
    assert out["players"]["sortAppliedStatTotal"] == {
        "sortPriority": 1,
        "sortAsc": False,
        "value": "102026",
    }
    assert "sortPercOwned" not in out["players"]


def test_invalid_position_lists_valid_values():
    with pytest.raises(FilterError, match="position must be one of") as exc:
        free_agent_filter(season=2026, position="FLEX", limit=10, sort="owned")
    for name in POSITION_SLOTS:
        assert name in str(exc.value)
    assert "FLEX" in str(exc.value)


def test_invalid_sort_lists_valid_values():
    with pytest.raises(FilterError, match="sort must be one of") as exc:
        free_agent_filter(season=2026, position=None, limit=10, sort="points")
    for name in SORTS:
        assert name in str(exc.value)


@pytest.mark.parametrize("limit", [0, MAX_LIMIT + 1, -3])
def test_limit_out_of_range(limit):
    with pytest.raises(FilterError, match=f"limit must be between 1 and {MAX_LIMIT}"):
        free_agent_filter(season=2026, position=None, limit=limit, sort="owned")


def test_each_call_returns_independent_dicts():
    a = free_agent_filter(season=2026, position=None, limit=10, sort="owned")
    b = free_agent_filter(season=2026, position=None, limit=10, sort="owned")
    a["players"]["filterStatus"]["value"].append("ONTEAM")
    assert b["players"]["filterStatus"]["value"] == ["FREEAGENT", "WAIVERS"]


@pytest.mark.parametrize("limit", [1, MAX_LIMIT])
def test_limit_boundaries_are_valid(limit):
    out = free_agent_filter(season=2026, position=None, limit=limit, sort="owned")
    assert out["players"]["limit"] == limit


@pytest.mark.parametrize("raw, expected", [("rb", "RB"), ("d/st", "D_ST"), ("D_ST", "D_ST")])
def test_normalize_position(raw, expected):
    assert normalize_position(raw) == expected
