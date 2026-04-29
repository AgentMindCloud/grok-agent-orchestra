"""Stub of ``grok_build_bridge.xai_client``."""

from __future__ import annotations

from typing import Any


class _Chat:
    def create(self, **_kwargs: Any) -> list[Any]:
        return []


class XAIClient:
    """No-op stand-in. Tests + docs builds never make a real call."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.chat = _Chat()

    def single_call(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []
