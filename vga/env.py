"""Local secrets: read .env from the repo root into the environment.

Plain KEY=VALUE lines, # comments, optional surrounding quotes. Real
environment variables always win, so an exported value is never overridden.
The loader runs once in cli.main(), before any key is resolved.
"""

from __future__ import annotations

import os
from pathlib import Path

DOTENV = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = DOTENV) -> list[str]:
    """Apply missing variables from a .env file. Returns variable names set."""
    loaded: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return loaded
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key.isidentifier():
            continue
        value = value.split(" #", 1)[0].strip().strip("'\"")
        if key not in os.environ and value:
            os.environ[key] = value
            loaded.append(key)
    return loaded
