"""MCPSource — stub server fixture, no real MCP SDK calls."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

# --------------------------------------------------------------------------- #
# Stub MCP client. Implements the same surface as _RealMCPClient + the
# simulated client so MCPSource doesn't know which transport it's talking
# to. Mirrors the unit-test pattern from test_image_providers_mock.py.
# --------------------------------------------------------------------------- #


class _StubMCPClient:
    closed = False

    def __init__(self, cfg: Any, *, tools: Sequence[str] = (), resources: Sequence[str] = (), tool_results: Mapping[str, str] | None = None) -> None:
        self.cfg = cfg
        self._tools = tuple(tools)
        self._resources = tuple(resources)
        self._tool_results = dict(tool_results or {})
        self.tool_calls: list[tuple[str, dict[str, Any]]] = []
        self.resource_reads: list[str] = []

    def list_tools(self) -> tuple[str, ...]:
        return self._tools

    def list_resources(self) -> tuple[str, ...]:
        return self._resources

    def read_resource(self, uri: str) -> str:
        self.resource_reads.append(uri)
        return f"resource body: {uri}"

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> str:
        self.tool_calls.append((name, dict(arguments)))
        return self._tool_results.get(name, f"called {name} with {arguments!r}")

    def close(self) -> None:
        self.__class__.closed = True


def _factory(*, fs_tools=("read_file", "list_directory", "search_files"), gh_tools=("search_issues", "list_pull_requests")):
    """Build a client_factory that returns one stub per server name."""
    instances: dict[str, _StubMCPClient] = {}

    def _make(cfg: Any) -> _StubMCPClient:
        if cfg.name == "filesystem":
            client = _StubMCPClient(
                cfg,
                tools=fs_tools,
                resources=("file:///docs/intro.md", "file:///docs/setup.md"),
            )
        elif cfg.name == "github":
            client = _StubMCPClient(
                cfg,
                tools=gh_tools,
                resources=("repo://owner/repo/issues/1",),
            )
        elif cfg.name == "broken":
            raise RuntimeError("boom — server failed to spawn")
        else:
            client = _StubMCPClient(cfg)
        instances[cfg.name] = client
        return client

    _make.instances = instances    # type: ignore[attr-defined]
    return _make


# --------------------------------------------------------------------------- #
# MCPSource basics.
# --------------------------------------------------------------------------- #


def test_collect_runs_lifecycle_and_emits_events() -> None:
    from grok_orchestra.sources.mcp_source import (
        MCPServerConfig,
        MCPSource,
    )

    factory = _factory()
    src = MCPSource(
        servers=(
            MCPServerConfig(name="filesystem", transport="stdio", command="npx", args=("-y", "@modelcontextprotocol/server-filesystem")),
        ),
        client_factory=factory,
    )

    events: list[dict[str, Any]] = []
    result = src.collect(goal="any", event_callback=events.append)

    types = [e["type"] for e in events]
    assert "mcp_connect" in types
    assert "mcp_resource_get" in types
    assert "mcp_disconnect" in types

    # Every Document carries the server name in metadata.
    assert result.documents
    for doc in result.documents:
        assert doc.metadata.get("mcp_server") == "filesystem"
    assert "MCP research findings" in result.brief
    assert result.stats["kind"] == "mcp"


def test_one_failed_server_does_not_break_collect() -> None:
    from grok_orchestra.sources.mcp_source import (
        MCPServerConfig,
        MCPSource,
    )

    factory = _factory()
    src = MCPSource(
        servers=(
            MCPServerConfig(name="broken", transport="stdio", command="x"),
            MCPServerConfig(name="filesystem", transport="stdio", command="npx"),
        ),
        client_factory=factory,
    )
    result = src.collect(goal="any")

    statuses = {s.name: s for s in src.server_statuses()}
    assert statuses["broken"].connected is False
    assert "boom" in (statuses["broken"].error or "")
    assert statuses["filesystem"].connected is True
    # Even with a partial failure, documents from the working server land.
    assert any(d.metadata.get("mcp_server") == "filesystem" for d in result.documents)


def test_resource_cache_prevents_reread_within_run() -> None:
    from grok_orchestra.sources.mcp_source import (
        MCPServerConfig,
        MCPSource,
    )

    factory = _factory()
    src = MCPSource(
        servers=(
            MCPServerConfig(name="filesystem", transport="stdio", command="npx"),
        ),
        client_factory=factory,
        max_resources_per_run=10,
    )
    src.connect()
    client = factory.instances["filesystem"]                  # type: ignore[attr-defined]

    src._read_resource("filesystem", "file:///docs/intro.md")
    src._read_resource("filesystem", "file:///docs/intro.md")
    # Cache hit on the second call — the underlying client only reads once.
    assert client.resource_reads == ["file:///docs/intro.md"]
    src.disconnect()


def test_call_tool_records_and_namespaces() -> None:
    from grok_orchestra.sources.mcp_source import (
        MCPServerConfig,
        MCPSource,
    )

    factory = _factory()
    src = MCPSource(
        servers=(
            MCPServerConfig(name="github", transport="stdio", command="npx"),
        ),
        client_factory=factory,
        allowed_roles=("Harper", "Benjamin"),
    )
    src.connect()
    call = src.call_tool(
        server="github",
        tool="search_issues",
        arguments={"q": "is:open label:bug"},
        role="Harper",
    )
    assert call.namespaced == "github__search_issues"
    assert call.is_error is False
    assert "search_issues" in call.output_text
    assert src.tool_calls()[0].namespaced == "github__search_issues"
    src.disconnect()


# --------------------------------------------------------------------------- #
# Backend ImportError surfaces a friendly message.
# --------------------------------------------------------------------------- #


def test_real_backend_raises_with_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the [mcp] extra, opening a real client points at install."""
    import sys

    # Hide the lazy backend module to simulate the [mcp] extra being absent.
    sys.modules.pop("grok_orchestra.sources._mcp_backend", None)

    from grok_orchestra.sources.mcp_source import (
        MCPConnectionError,
        MCPServerConfig,
        MCPSource,
    )

    src = MCPSource(
        servers=(MCPServerConfig(name="x", transport="stdio", command="x"),),
    )
    cfg = src.servers[0]
    # Force the import path inside _open_client. We can't easily provoke
    # ImportError on a real environment without the SDK, so we simulate
    # the contract: the backend module raises ImportError → MCPSource
    # wraps it in MCPConnectionError. Patch open_real_client to raise.
    import grok_orchestra.sources._mcp_backend as backend

    def _boom(_cfg):    # type: ignore[no-untyped-def]
        raise ImportError("MCP SDK is not installed.")

    monkeypatch.setattr(backend, "open_real_client", _boom)
    with pytest.raises(MCPConnectionError, match="grok-agent-orchestra\\[mcp\\]"):
        src._open_client(cfg)
