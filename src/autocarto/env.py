"""Minimal, dependency-free .env loader.

Reads a `.env` file (KEY=VALUE per line, `#` comments, optional surrounding
quotes) and returns a dict — used to supply the Census and NVIDIA API keys
without adding python-dotenv as a dependency. Secrets are never logged: the
loader returns values, callers pass them straight to request headers, and
nothing here prints or persists them.

`.env` is gitignored (see .gitignore) — these keys must never be committed.
`.env.example` documents the required variable names with placeholder values.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ENV_PATH = REPO_ROOT / ".env"


def load_env(path: Optional[Path] = None) -> Dict[str, str]:
    """Parse a .env file into a dict. Missing file -> empty dict (not an error)."""
    path = path or DEFAULT_ENV_PATH
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


def get_key(name: str, *, env_path: Optional[Path] = None, required: bool = True) -> Optional[str]:
    """Resolve an API key: real environment variable first, then .env file.

    The process environment takes precedence so CI / a shell export can
    override the file without editing it. Returns None (or raises, if
    required) when the key is available in neither place.
    """
    val = os.environ.get(name)
    if val:
        return val
    val = load_env(env_path).get(name)
    if val:
        return val
    if required:
        raise RuntimeError(
            f"{name} not found in the environment or {DEFAULT_ENV_PATH.name}. "
            f"Set it as an environment variable or add it to .env "
            f"(see .env.example for the expected variable names)."
        )
    return None
