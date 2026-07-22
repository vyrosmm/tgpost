"""Configuration loading for tgpost.

Settings can come from three places, in increasing priority:

1. a config file — ``.tgpost.toml`` in the current directory, or ``~/.tgpost.toml``
2. environment variables — ``TGPOST_TOKEN`` / ``TGPOST_CHAT``
3. command line flags — ``--token`` / ``--chat``

The file is optional; nothing here is required for tgpost to work.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:                                    # Python 3.11+
    import tomllib
except ModuleNotFoundError:             # pragma: no cover - 3.9/3.10
    tomllib = None                      # type: ignore[assignment]

__all__ = ["load_file", "resolve"]

FILENAME = ".tgpost.toml"


def _candidates() -> list[Path]:
    return [Path.cwd() / FILENAME, Path.home() / FILENAME]


def load_file() -> dict[str, Any]:
    """Read the first config file that exists. Returns {} when there is none."""
    if tomllib is None:
        return {}
    for path in _candidates():
        if not path.is_file():
            continue
        try:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
        except Exception:
            return {}                   # a broken file must not break posting
        return data.get("tgpost", data) if isinstance(data, dict) else {}
    return {}


def _env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def resolve(key: str, cli_value: str | None = None) -> str:
    """Resolve one setting across CLI flag > environment > config file."""
    if cli_value:
        return cli_value
    env_value = _env(f"TGPOST_{key.upper()}", f"TELEGRAM_{key.upper()}")
    if env_value:
        return env_value
    value = load_file().get(key)
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    return str(value).strip() if value else ""
