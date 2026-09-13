import pytest

from fantasy_mcp.filters import MAX_LIMIT, POSITION_SLOTS, SORTS, free_agent_filter

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


def test_projected_sort_uses_season_stat_id():
    out = free_agent_filter(season=2026, position=None, limit=10, sort="projected")
    assert out["players"]["sortAppliedStatTotal"] == {
        "sortPriority": 1,
        "sortAsc": False,
        "value": "102026",
    }
    assert "sortPercOwned" not in out["players"]


def test_invalid_position_lists_valid_values():
    with pytest.raises(ValueError, match="position must be one of") as exc:
        free_agent_filter(season=2026, position="FLEX", limit=10, sort="owned")
    for name in POSITION_SLOTS:
        assert name in str(exc.value)
    assert "FLEX" in str(exc.value)


def test_invalid_sort_lists_valid_values():
    with pytest.raises(ValueError, match="sort must be one of") as exc:
        free_agent_filter(season=2026, position=None, limit=10, sort="points")
    for name in SORTS:
        assert name in str(exc.value)


@pytest.mark.parametrize("limit", [0, MAX_LIMIT + 1, -3])
def test_limit_out_of_range(limit):
    with pytest.raises(ValueError, match=f"limit must be between 1 and {MAX_LIMIT}"):
        free_agent_filter(season=2026, position=None, limit=limit, sort="owned")
