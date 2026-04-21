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


def _stub_audit_x_post(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"approved": True, "flagged": False}


def _stub_deploy_to_target(*_args: Any, **_kwargs: Any) -> str:
    return "https://example.test/deployed"


def _stub_section(console: Any, title: str) -> None:
    console.rule(title, style="cyan")


class _StubChat:
    """Minimal stand-in for ``XAIClient.chat``.

    Tests typically reassign ``client.chat`` to a MagicMock, but having a
    real attribute present on construction makes the import path exercise
    the same code path it would hit in production.
    """

    def create(self, **_kwargs: Any) -> list[Any]:
        return []


class _StubXAIClient:
    """Stand-in for ``grok_build_bridge.xai_client.XAIClient``.

    Accepts any kwargs so subclasses can be instantiated in tests without
    having to mirror the real Bridge constructor.
    """

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.chat = _StubChat()


class _StubRateLimitError(Exception):
    """Stand-in for ``xai_sdk.errors.RateLimitError``."""


def _stub_x_search(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"type": "x_search"}


def _stub_web_search(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"type": "web_search"}


def _stub_code_execution(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"type": "code_execution"}


def _install_bridge_stub() -> None:
    if "grok_build_bridge" in sys.modules:
        return

    pkg = types.ModuleType("grok_build_bridge")
    parser_mod = types.ModuleType("grok_build_bridge.parser")
    safety_mod = types.ModuleType("grok_build_bridge.safety")
    deploy_mod = types.ModuleType("grok_build_bridge.deploy")
    xai_mod = types.ModuleType("grok_build_bridge.xai_client")
    console_mod = types.ModuleType("grok_build_bridge._console")

    parser_mod.load_yaml = _stub_load_yaml
    parser_mod.BridgeConfigError = _StubBridgeConfigError
    safety_mod.audit_x_post = _stub_audit_x_post
    deploy_mod.deploy_to_target = _stub_deploy_to_target
    xai_mod.XAIClient = _StubXAIClient
    console_mod.console = Console()
    console_mod.section = _stub_section

    pkg._console = console_mod  # type: ignore[attr-defined]

    sys.modules["grok_build_bridge"] = pkg
    sys.modules["grok_build_bridge.parser"] = parser_mod
    sys.modules["grok_build_bridge.safety"] = safety_mod
    sys.modules["grok_build_bridge.deploy"] = deploy_mod
    sys.modules["grok_build_bridge.xai_client"] = xai_mod
    sys.modules["grok_build_bridge._console"] = console_mod


def _install_xai_sdk_stub() -> None:
    if "xai_sdk" in sys.modules:
        return

    pkg = types.ModuleType("xai_sdk")
    tools_mod = types.ModuleType("xai_sdk.tools")
    errors_mod = types.ModuleType("xai_sdk.errors")

    tools_mod.x_search = _stub_x_search
    tools_mod.web_search = _stub_web_search
    tools_mod.code_execution = _stub_code_execution

    errors_mod.RateLimitError = _StubRateLimitError
    pkg.RateLimitError = _StubRateLimitError  # type: ignore[attr-defined]

    sys.modules["xai_sdk"] = pkg
    sys.modules["xai_sdk.tools"] = tools_mod
    sys.modules["xai_sdk.errors"] = errors_mod


_install_bridge_stub()
_install_xai_sdk_stub()
