"""Per-user saved ESPN settings (written by the in-chat setup card).

Lives in the platform config directory, e.g.
``~/Library/Application Support/fantasy-mcp/config.json`` on macOS,
``%APPDATA%\\fantasy-mcp\\config.json`` on Windows, ``~/.config/fantasy-mcp/config.json``
on Linux. Values are the same ESPN_* keys the environment uses.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from platformdirs import user_config_dir

KEYS = ("ESPN_S2", "ESPN_SWID", "ESPN_LEAGUE_ID", "ESPN_SEASON", "ESPN_TEAM_ID")


def config_path() -> Path:
    return Path(user_config_dir("fantasy-mcp", appauthor=False)) / "config.json"


def load() -> dict[str, str]:
    """Saved values, or {} if the file is missing or unreadable."""
    try:
        raw = json.loads(config_path().read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: str(v) for k, v in raw.items() if k in KEYS and isinstance(v, (str, int))}


def save(values: dict[str, str | None]) -> Path:
    """Write the known, non-empty values (replacing the file) with owner-only permissions."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = {k: v for k, v in values.items() if k in KEYS and v}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(kept, f, indent=2)
    os.chmod(path, 0o600)
    return path
