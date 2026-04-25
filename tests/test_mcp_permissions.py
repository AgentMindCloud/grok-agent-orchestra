"""MCPSource permission gate — read-only blocks destructive tools."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest


class _StubMCPClient:
    def __init__(self, cfg: Any) -> None:
        self.cfg = cfg
        self.tool_calls: list[tuple[str, dict[str, Any]]] = []

    def list_tools(self) -> tuple[str, ...]:
        # Mix of safe + destructive names.
        return (
            "search_files",
            "read_file",
            "list_directory",
            "create_file",
            "delete_file",
            "exec_command",
            "update_record",
        )

    def list_resources(self) -> tuple[str, ...]:
        return ()

    def read_resource(self, _uri: str) -> str:
        return ""

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> str:
        self.tool_calls.append((name, dict(arguments)))
        return f"called {name}"

    def close(self) -> None:
        return None


def _factory(cfg):    # type: ignore[no-untyped-def]
    return _StubMCPClient(cfg)


# --------------------------------------------------------------------------- #
# Default: read-only mode blocks mutations across the canonical patterns.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "tool, expected",
    [
        ("read_file", True),
        ("list_directory", True),
        ("search_files", True),
        ("create_file", False),     # contains "create"
        ("delete_file", False),     # contains "delete"
        ("exec_command", False),    # contains "exec"
        ("update_record", False),   # contains "update"
        ("write_log", False),       # contains "write"
        ("set_value", False),       # leading set_
        ("file_delete", False),     # trailing _delete
        ("ping", True),
    ],
)
def test_read_only_gate_blocks_mutation_tool_names(tool: str, expected: bool) -> None:
    from grok_orchestra.sources.mcp_source import (
        MCPServerConfig,
        MCPSource,
    )

    src = MCPSource(
        servers=(MCPServerConfig(name="fs", transport="stdio", command="x"),),
        allow_mutations=False,
    )
    assert src.is_tool_allowed(server="fs", tool=tool, role="Harper") is expected


def test_call_tool_raises_permission_denied_for_destructive_call() -> None:
    from grok_orchestra.sources.mcp_source import (
        MCPPermissionDenied,
        MCPServerConfig,
        MCPSource,
    )

    src = MCPSource(
        servers=(MCPServerConfig(name="fs", transport="stdio", command="x"),),
        client_factory=_factory,
        allow_mutations=False,
    )
    src.connect()
    with pytest.raises(MCPPermissionDenied):
        src.call_tool(server="fs", tool="delete_file", arguments={"path": "/x"})
    src.disconnect()


def test_allow_mutations_unblocks_destructive_call() -> None:
    from grok_orchestra.sources.mcp_source import (
        MCPServerConfig,
        MCPSource,
    )

    src = MCPSource(
        servers=(MCPServerConfig(name="fs", transport="stdio", command="x"),),
        client_factory=_factory,
        allow_mutations=True,
    )
    src.connect()
    call = src.call_tool(
        server="fs", tool="delete_file", arguments={"path": "/x"}, role="Harper"
    )
    assert call.namespaced == "fs__delete_file"
    src.disconnect()


def test_per_server_override_takes_precedence_over_source_default() -> None:
    from grok_orchestra.sources.mcp_source import (
        MCPServerConfig,
        MCPSource,
    )

    src = MCPSource(
        servers=(
            MCPServerConfig(name="fs", transport="stdio", command="x"),
            MCPServerConfig(
                name="db", transport="stdio", command="x", allow_mutations=True
            ),
        ),
        allow_mutations=False,
    )
    assert not src.is_tool_allowed(server="fs", tool="delete_record", role="Harper")
    assert src.is_tool_allowed(server="db", tool="delete_record", role="Harper")


def test_role_gate_blocks_disallowed_role() -> None:
    from grok_orchestra.sources.mcp_source import (
        MCPServerConfig,
        MCPSource,
    )

    src = MCPSource(
        servers=(MCPServerConfig(name="fs", transport="stdio", command="x"),),
        allowed_roles=("Harper",),
    )
    assert src.is_tool_allowed(server="fs", tool="read_file", role="Harper")
    assert not src.is_tool_allowed(server="fs", tool="read_file", role="Lucas")


def test_unknown_server_is_never_allowed() -> None:
    from grok_orchestra.sources.mcp_source import MCPSource

    src = MCPSource(servers=())
    assert not src.is_tool_allowed(server="nope", tool="read_file", role="Harper")
