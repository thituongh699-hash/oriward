"""Read pre-rename local settings without rewriting credentials or user data.

All new interfaces use ORIWARD_*. These two old identifiers are intentionally
isolated here so existing local databases and explicit settings still work.
"""
from __future__ import annotations

import os

LEGACY_ENV_PREFIX = "CAREEROS_"
LEGACY_DATABASE_NAME = "careeros.sqlite3"


def environment(name: str, default=None):
    """Prefer an explicit new setting, including empty/disabled values."""
    if name in os.environ:
        return os.environ[name]
    if not name.startswith("ORIWARD_"):
        raise ValueError("Expected an ORIWARD_ environment variable")
    return os.environ.get(LEGACY_ENV_PREFIX + name[len("ORIWARD_"):], default)
