"""Stub of ``grok_build_bridge.parser``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class BridgeConfigError(Exception):
    """Stand-in for the real Bridge config-validation error."""


def load_yaml(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)
