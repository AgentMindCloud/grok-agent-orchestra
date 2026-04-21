"""Test fixtures and fakes.

Orchestra treats ``grok_build_bridge`` as a hard dependency. We install a
minimal stub in ``sys.modules`` before any test module imports
:mod:`grok_orchestra`, because the real Bridge package is not available in
the isolated test environment used by CI for this repository.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console


class _StubBridgeConfigError(Exception):
    """Stand-in for ``grok_build_bridge.parser.BridgeConfigError``."""


def _stub_load_yaml(path: str | Path) -> Any:
    """Stand-in for ``grok_build_bridge.parser.load_yaml``.

    Real Bridge validates against its own schema; for Orchestra tests we only
    need the raw dict. Orchestra's extension schema runs on top.
    """
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _stub_audit_x_post(*_args: Any, **_kwargs: Any) -> bool:
    return True


class _StubXAIClient:
    """Stand-in for ``grok_build_bridge.xai_client.XAIClient``."""


def _install_bridge_stub() -> None:
    if "grok_build_bridge" in sys.modules:
        return

    pkg = types.ModuleType("grok_build_bridge")
    parser_mod = types.ModuleType("grok_build_bridge.parser")
    safety_mod = types.ModuleType("grok_build_bridge.safety")
    xai_mod = types.ModuleType("grok_build_bridge.xai_client")
    console_mod = types.ModuleType("grok_build_bridge._console")

    parser_mod.load_yaml = _stub_load_yaml
    parser_mod.BridgeConfigError = _StubBridgeConfigError
    safety_mod.audit_x_post = _stub_audit_x_post
    xai_mod.XAIClient = _StubXAIClient
    console_mod.console = Console()

    pkg._console = console_mod  # type: ignore[attr-defined]

    sys.modules["grok_build_bridge"] = pkg
    sys.modules["grok_build_bridge.parser"] = parser_mod
    sys.modules["grok_build_bridge.safety"] = safety_mod
    sys.modules["grok_build_bridge.xai_client"] = xai_mod
    sys.modules["grok_build_bridge._console"] = console_mod


_install_bridge_stub()
