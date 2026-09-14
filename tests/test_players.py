import pytest

from fantasy_mcp.espn import EspnError
from fantasy_mcp.players import resolve_player


def test_exact_match(players_index):
    assert resolve_player("Jonathan Taylor", players_index) == 4242335


def test_casefold_and_punctuation_insensitive(players_index):
    assert resolve_player("a.j. brown", players_index) == 1001
    assert resolve_player("  AJ   BROWN ", players_index) == 1001


def test_unique_substring(players_index):
    assert resolve_player("kraft", players_index) == 4572680


def test_ambiguous_substring_lists_candidates_by_ownership(players_index):
    with pytest.raises(EspnError) as exc:
        resolve_player("tucker", players_index)
    msg = str(exc.value)
    assert "Tucker Kraft (TE, GB, id 4572680)" in msg
    assert "Justin Tucker (K, BAL, id 15683)" in msg
    assert "Tre Tucker (WR, LV, id 4362628)" in msg
    assert msg.index("Tucker Kraft") < msg.index("Justin Tucker") < msg.index("Tre Tucker")
    assert "player_id" in msg


def test_duplicate_exact_names_are_ambiguous(players_index):
    with pytest.raises(EspnError, match="id 2001") as exc:
        resolve_player("Sam Smith", players_index)
    assert "id 2002" in str(exc.value)


def test_no_match(players_index):
    with pytest.raises(EspnError, match="No active player matches 'Nobody Real'"):
        resolve_player("Nobody Real", players_index)


@pytest.mark.parametrize("blank", ["", "   ", ". '"])
def test_blank_name_is_rejected(players_index, blank):
    with pytest.raises(EspnError, match="name is required"):
        resolve_player(blank, players_index)


def test_entry_without_name_does_not_crash(players_index):
    players_index.append({"id": 3001, "defaultPositionId": 2, "proTeamId": 11})
    players_index.append({"id": 3002, "fullName": "Sam Smithers", "defaultPositionId": 2, "proTeamId": 11})
    assert resolve_player("Jonathan Taylor", players_index) == 4242335
    with pytest.raises(EspnError) as exc:
        resolve_player("smith", players_index)
    assert "Sam Smithers" in str(exc.value)
    assert "None" not in str(exc.value)
