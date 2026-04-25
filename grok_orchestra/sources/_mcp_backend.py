"""Real MCP SDK shim. Import-protected behind ``[mcp]`` extra.

This module is only imported by :mod:`grok_orchestra.sources.mcp_source`
when ``MCPSource`` runs in non-simulated mode. Keeping the SDK import
quarantined here means the rest of the package stays importable even
when the optional ``mcp`` PyPI dependency is missing.

Concrete clients implement four methods so :class:`MCPSource` doesn't
have to know which transport it's talking to:

- ``list_tools() -> Sequence[str]``
- ``list_resources() -> Sequence[str]``
- ``read_resource(uri) -> str``
- ``call_tool(name, arguments) -> str``
- ``close() -> None``

The MCP SDK is async-first; we run it on a private ``anyio`` event
loop per client so callers stay synchronous (matching the rest of the
Source layer).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:                      # pragma: no cover
    from grok_orchestra.sources.mcp_source import MCPServerConfig

__all__ = ["open_real_client"]

_log = logging.getLogger(__name__)


def open_real_client(cfg: MCPServerConfig) -> Any:    # noqa: F821
    """Construct + connect a real MCP client for ``cfg``.

    Raises :class:`ImportError` when the ``mcp`` SDK is not installed.
    """
    try:
        import anyio  # noqa: F401
        import mcp  # noqa: F401
    except ImportError as exc:                             # pragma: no cover
        raise ImportError(
            "MCP SDK is not installed. Install with: "
            "pip install 'grok-agent-orchestra[mcp]'"
        ) from exc

    if cfg.transport == "stdio":
        return _RealMCPClient(cfg, transport="stdio")
    if cfg.transport in ("http", "websocket"):
        return _RealMCPClient(cfg, transport=cfg.transport)
    raise ValueError(f"unsupported MCP transport: {cfg.transport}")


class _RealMCPClient:
    """Async MCP session driven from a private background thread.

    The MCP SDK exposes coroutines; we own one anyio event loop per
    client and proxy synchronous calls onto it. This keeps every
    Source synchronous from the runner's POV and means a slow MCP
    server cannot stall the main thread beyond the operation itself.
    """

    def __init__(self, cfg: MCPServerConfig, *, transport: str) -> None:    # noqa: F821
        import anyio
        from mcp import ClientSession

        self._cfg = cfg
        self._transport = transport
        self._anyio = anyio
        self._ClientSession = ClientSession

        self._session: Any = None
        self._loop_thread: threading.Thread | None = None
        self._loop_ready = threading.Event()
        self._loop: Any = None
        self._exit_stack: Any = None
        self._tools: tuple[str, ...] = ()
        self._resources: tuple[str, ...] = ()

        self._start_loop()
        self._connect()

    # -- thread / loop plumbing ------------------------------------------------

    def _start_loop(self) -> None:
        import asyncio

        def _runner() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop_ready.set()
            try:
                self._loop.run_forever()
            finally:
                self._loop.close()

        self._loop_thread = threading.Thread(
            target=_runner, name=f"mcp-{self._cfg.name}", daemon=True
        )
        self._loop_thread.start()
        self._loop_ready.wait(timeout=5.0)

    def _run_coro(self, coro: Any, *, timeout: float = 30.0) -> Any:
        import asyncio

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # -- connection lifecycle --------------------------------------------------

    def _connect(self) -> None:
        async def _impl() -> None:
            from contextlib import AsyncExitStack

            stack = AsyncExitStack()
            await stack.__aenter__()
            self._exit_stack = stack

            if self._transport == "stdio":
                from mcp.client.stdio import StdioServerParameters, stdio_client

                params = StdioServerParameters(
                    command=self._cfg.command,
                    args=list(self._cfg.args),
                    env=dict(self._cfg.env) or None,
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            elif self._transport == "http":
                from mcp.client.streamable_http import streamablehttp_client

                headers: dict[str, str] = {}
                if self._cfg.auth_type == "bearer" and self._cfg.auth_token:
                    headers["Authorization"] = f"Bearer {self._cfg.auth_token}"
                read, write, _close = await stack.enter_async_context(
                    streamablehttp_client(self._cfg.url, headers=headers or None)
                )
            else:                                          # websocket
                from mcp.client.websocket import websocket_client

                headers = {}
                if self._cfg.auth_type == "bearer" and self._cfg.auth_token:
                    headers["Authorization"] = f"Bearer {self._cfg.auth_token}"
                read, write = await stack.enter_async_context(
                    websocket_client(self._cfg.url, headers=headers or None)
                )

            session = await stack.enter_async_context(self._ClientSession(read, write))
            await session.initialize()
            self._session = session

            tools_resp = await session.list_tools()
            resources_resp = await session.list_resources()
            self._tools = tuple(getattr(t, "name", str(t)) for t in tools_resp.tools)
            self._resources = tuple(
                getattr(r, "uri", str(r)) for r in resources_resp.resources
            )

        self._run_coro(_impl())

    def list_tools(self) -> Sequence[str]:
        return self._tools

    def list_resources(self) -> Sequence[str]:
        return self._resources

    def read_resource(self, uri: str) -> str:
        async def _impl() -> str:
            result = await self._session.read_resource(uri)
            parts: list[str] = []
            for entry in getattr(result, "contents", ()) or ():
                text = getattr(entry, "text", None)
                if text:
                    parts.append(str(text))
            return "\n".join(parts)
        return self._run_coro(_impl())

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> str:
        async def _impl() -> str:
            result = await self._session.call_tool(name, dict(arguments))
            parts: list[str] = []
            for entry in getattr(result, "content", ()) or ():
                text = getattr(entry, "text", None)
                if text:
                    parts.append(str(text))
            return "\n".join(parts)
        return self._run_coro(_impl())

    def close(self) -> None:
        if self._loop is None:
            return
        async def _impl() -> None:
            if self._exit_stack is not None:
                try:
                    await self._exit_stack.aclose()
                except Exception as exc:  # noqa: BLE001
                    _log.warning("MCP exit_stack close failed: %s", exc)

        try:
            self._run_coro(_impl(), timeout=5.0)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._loop_thread is not None:
                self._loop_thread.join(timeout=5.0)
