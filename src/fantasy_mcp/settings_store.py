"""Per-user saved ESPN settings (written by the in-chat setup card).

Lives in the platform config directory, e.g.
``~/Library/Application Support/fantasy-mcp/config.json`` on macOS,
``%APPDATA%\\fantasy-mcp\\config.json`` on Windows, ``~/.config/fantasy-mcp/config.json``
on Linux. Values are the same ESPN_* keys the environment uses.

On Windows the 0600 mode only affects the read-only attribute; confidentiality there
comes from the per-user %APPDATA% ACL.
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
        raw = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        k: str(v)
        for k, v in raw.items()
        if k in KEYS and (isinstance(v, str) or (isinstance(v, int) and not isinstance(v, bool)))
    }


def save(values: dict[str, str | None]) -> Path:
    """Write the known, non-empty values (replacing the file) with owner-only permissions."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = {k: str(v) for k, v in values.items() if k in KEYS and v}
    payload = json.dumps(kept, indent=2)  # serialize first so a bad value can't truncate a good file
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)  # tighten a pre-existing looser file before any secret is written
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(payload)
    return path
