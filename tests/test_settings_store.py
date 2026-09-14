import json
import os
import stat
import sys

import pytest

from fantasy_mcp import settings_store


def test_load_missing_file_is_empty(isolated_config_path):
    assert not isolated_config_path.exists()
    assert settings_store.load() == {}


def test_save_then_load_round_trip(isolated_config_path):
    path = settings_store.save({"ESPN_S2": "abc", "ESPN_SWID": "{X}", "ESPN_LEAGUE_ID": "42"})
    assert path == isolated_config_path
    assert settings_store.load() == {"ESPN_S2": "abc", "ESPN_SWID": "{X}", "ESPN_LEAGUE_ID": "42"}


def test_save_drops_unknown_and_empty_values(isolated_config_path):
    settings_store.save({"ESPN_S2": "abc", "ESPN_SWID": "", "ESPN_TEAM_ID": None, "OTHER": "x"})
    assert settings_store.load() == {"ESPN_S2": "abc"}


def test_save_overwrites_previous_file(isolated_config_path):
    settings_store.save({"ESPN_S2": "old", "ESPN_LEAGUE_ID": "1"})
    settings_store.save({"ESPN_S2": "new"})
    assert settings_store.load() == {"ESPN_S2": "new"}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_save_sets_owner_only_permissions(isolated_config_path):
    settings_store.save({"ESPN_S2": "abc"})
    mode = stat.S_IMODE(os.stat(isolated_config_path).st_mode)
    assert mode == 0o600


def test_load_corrupt_file_is_empty(isolated_config_path):
    isolated_config_path.parent.mkdir(parents=True)
    isolated_config_path.write_text("{not json")
    assert settings_store.load() == {}


def test_load_ignores_non_string_and_unknown_entries(isolated_config_path):
    isolated_config_path.parent.mkdir(parents=True)
    isolated_config_path.write_text(json.dumps({"ESPN_S2": "abc", "ESPN_LEAGUE_ID": 42, "junk": "x"}))
    assert settings_store.load() == {"ESPN_S2": "abc", "ESPN_LEAGUE_ID": "42"}
