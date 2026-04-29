"""Stub of ``grok_build_bridge.safety``."""

from __future__ import annotations

from typing import Any


def audit_x_post(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"approved": True, "flagged": False}


def scan_generated_code(_files: Any, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"safe": True, "issues": []}
