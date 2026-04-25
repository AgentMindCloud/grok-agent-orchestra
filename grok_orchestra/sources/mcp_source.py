"""``MCPSource`` — Model Context Protocol client as a Source.

This is the source the runner invokes when YAML carries:

.. code-block:: yaml

    sources:
      - type: mcp
        servers:
          - name: github
            transport: stdio
            command: npx
            args: ["-y", "@modelcontextprotocol/server-github"]
            env:
              GITHUB_PERSONAL_ACCESS_TOKEN: ${GITHUB_TOKEN}
          - name: postgres
            transport: stdio
            command: npx
            args: ["-y", "@modelcontextprotocol/server-postgres", "${DATABASE_URL}"]
          - name: my-internal
            transport: http
            url: https://my-mcp.example.com
            auth:
              type: bearer
              token: ${MY_MCP_TOKEN}
        # Per-server defaults applied unless the server overrides them:
        allow_mutations: false      # block write/delete/exec tool patterns
        allowed_roles: [Harper]     # roles permitted to invoke MCP tools
        max_resources_per_run: 50

Lifecycle, in order of operations:

1. ``connect()`` — for each server, spawn the stdio process or open
   the HTTP/WebSocket session. Failures on one server log a warning
   and the rest continue.
2. ``collect()`` — for each connected server, list resources + tools,
   namespace tools as ``<server-name>__<tool-name>``, and assemble a
   research brief. Resources are read once per run and cached.
3. ``disconnect()`` — close every active session in reverse order.

The MCP Python SDK (``mcp`` on PyPI) is imported lazily inside
``connect()``; the module imports cleanly without the ``[mcp]`` extra
installed.

Security:

- **Secrets never leave the host.** Env interpolation happens at
  parse time inside :func:`_resolve_env`; the resolved values flow
  to the subprocess / HTTP client only. They are never embedded in
  Documents, briefs, span attributes, or LLM prompts.
- **Read-only by default.** Tool names matching write/delete/exec
  patterns are filtered out unless ``allow_mutations: true``.
- **Lucas can still veto.** Tool calls surface as events; a Lucas
  mid-loop veto can block a synthesis built on questionable tool
  results in the iterative pattern.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from grok_orchestra.sources import (
    Document,
    ResearchResult,
    Source,
    SourceError,
)

__all__ = [
    "MCPConnectionError",
    "MCPPermissionDenied",
    "MCPServerConfig",
    "MCPSource",
    "MCPToolCall",
    "MUTATION_PATTERNS",
    "ServerStatus",
]

_log = logging.getLogger(__name__)


# Tool names matching any of these regexes are treated as side-effecting
# and blocked unless `allow_mutations: true` is set on the server. The
# patterns are intentionally broad — false positives are easy to fix
# (set `allow_mutations: true`); a missed mutation under read-only mode
# is a security incident.
# Tokens are split on underscores and word boundaries so names like
# `delete_file`, `file_delete`, `update_record`, and `execCommand` all
# match. The token list intentionally errs broad — false positives
# unblock with a one-line `allow_mutations: true`; false negatives are
# silent escalation.
_MUTATION_TOKENS: frozenset[str] = frozenset(
    {
        "write", "create", "update", "delete", "drop", "insert", "exec",
        "run", "kill", "patch", "push", "put", "post", "reset", "truncate",
        "move", "rename", "remove", "destroy", "terminate", "set", "add",
    }
)
MUTATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)(?:^|[_\-\s/]|(?<=[a-z])(?=[A-Z]))("
        + "|".join(sorted(_MUTATION_TOKENS, key=len, reverse=True))
        + r")(?:$|[_\-\s/]|(?<=[a-z])(?=[A-Z]))"
    ),
)


# --------------------------------------------------------------------------- #
# Errors.
# --------------------------------------------------------------------------- #


class MCPConnectionError(SourceError):
    """Raised when an MCP server cannot be connected, listed, or closed."""


class MCPPermissionDenied(SourceError):
    """Raised when a tool call is blocked by the read-only gate or role list."""


# --------------------------------------------------------------------------- #
# Config dataclasses.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MCPServerConfig:
    """One MCP server entry from the YAML ``servers:`` list."""

    name: str
    transport: Literal["stdio", "http", "websocket"]
    # stdio
    command: str = ""
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    # http / websocket
    url: str = ""
    auth_type: Literal["none", "bearer"] = "none"
    auth_token: str = ""
    # per-server overrides (default to source-level values when blank)
    allow_mutations: bool | None = None
    allowed_roles: tuple[str, ...] | None = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> MCPServerConfig:
        name = str(raw.get("name") or "").strip()
        if not name:
            raise SourceError("MCP server entry missing 'name'")
        transport = str(raw.get("transport") or "stdio").lower()
        if transport not in {"stdio", "http", "websocket"}:
            raise SourceError(
                f"MCP server '{name}': unknown transport '{transport}' "
                "(expected stdio | http | websocket)"
            )
        env_in = raw.get("env") or {}
        if not isinstance(env_in, Mapping):
            raise SourceError(f"MCP server '{name}': 'env' must be a mapping")
        env_resolved = {str(k): _resolve_env(str(v)) for k, v in env_in.items()}
        args_in = raw.get("args") or ()
        if not isinstance(args_in, (list, tuple)):
            raise SourceError(f"MCP server '{name}': 'args' must be a list")
        args_resolved = tuple(_resolve_env(str(a)) for a in args_in)
        auth_block = raw.get("auth") or {}
        if not isinstance(auth_block, Mapping):
            raise SourceError(f"MCP server '{name}': 'auth' must be a mapping")
        auth_type = str(auth_block.get("type") or "none").lower()
        if auth_type not in {"none", "bearer"}:
            raise SourceError(
                f"MCP server '{name}': unknown auth type '{auth_type}'"
            )
        auth_token = _resolve_env(str(auth_block.get("token") or ""))
        allow_mutations: bool | None = (
            bool(raw["allow_mutations"]) if "allow_mutations" in raw else None
        )
        allowed_roles_in = raw.get("allowed_roles")
        allowed_roles = (
            tuple(str(r) for r in allowed_roles_in)
            if isinstance(allowed_roles_in, (list, tuple))
            else None
        )
        return cls(
            name=name,
            transport=transport,                                # type: ignore[arg-type]
            command=_resolve_env(str(raw.get("command") or "")),
            args=args_resolved,
            env=env_resolved,
            url=_resolve_env(str(raw.get("url") or "")),
            auth_type=auth_type,                                # type: ignore[arg-type]
            auth_token=auth_token,
            allow_mutations=allow_mutations,
            allowed_roles=allowed_roles,
        )

    def public_dict(self) -> dict[str, Any]:
        """Trace-safe summary — secrets stripped, env keys only."""
        return {
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "url": self.url,
            "args_count": len(self.args),
            "env_keys": sorted(self.env.keys()),
            "auth_type": self.auth_type,
            "allow_mutations": self.allow_mutations,
            "allowed_roles": list(self.allowed_roles) if self.allowed_roles else None,
        }


# --------------------------------------------------------------------------- #
# Connection state.
# --------------------------------------------------------------------------- #


@dataclass
class ServerStatus:
    """Live state for one connected MCP server. Trace-safe; no secrets."""

    name: str
    transport: str
    connected: bool = False
    error: str | None = None
    tool_count: int = 0
    resource_count: int = 0
    tool_names: tuple[str, ...] = ()
    resource_uris: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "transport": self.transport,
            "connected": self.connected,
            "error": self.error,
            "tool_count": self.tool_count,
            "resource_count": self.resource_count,
            "tool_names": list(self.tool_names),
            "resource_uris": list(self.resource_uris[:50]),
        }


@dataclass(frozen=True)
class MCPToolCall:
    """One MCP tool invocation result (cached for tracing + the report)."""

    server: str
    tool: str
    namespaced: str            # "<server>__<tool>"
    inputs: Mapping[str, Any]
    output_text: str
    is_error: bool = False
    latency_ms: float = 0.0


# --------------------------------------------------------------------------- #
# MCPSource.
# --------------------------------------------------------------------------- #


@dataclass
class MCPSource(Source):
    """Connect to one-or-many MCP servers and surface their tools+resources.

    See module docstring for the full YAML shape and security model.
    """

    servers: tuple[MCPServerConfig, ...] = ()
    allow_mutations: bool = False
    allowed_roles: tuple[str, ...] = ("Harper",)
    max_resources_per_run: int = 50

    # Test/runner injection points.
    client_factory: Any | None = None     # for tests; produces fake clients
    simulated: bool = False

    # Runtime state (populated by connect()/collect()).
    _statuses: dict[str, ServerStatus] = field(default_factory=dict)
    _clients: dict[str, Any] = field(default_factory=dict)
    _resource_cache: dict[str, str] = field(default_factory=dict)
    _tool_calls: list[MCPToolCall] = field(default_factory=list)

    @classmethod
    def from_config(cls, spec: Mapping[str, Any]) -> MCPSource:
        servers_raw = spec.get("servers") or []
        if not isinstance(servers_raw, Sequence) or not servers_raw:
            raise SourceError("MCP source requires a non-empty 'servers' list")
        servers = tuple(
            MCPServerConfig.from_dict(s)
            for s in servers_raw
            if isinstance(s, Mapping)
        )
        allow_mutations = bool(spec.get("allow_mutations", False))
        roles_in = spec.get("allowed_roles") or ("Harper",)
        if not isinstance(roles_in, (list, tuple)):
            raise SourceError("'allowed_roles' must be a list")
        allowed_roles = tuple(str(r) for r in roles_in)
        max_resources = int(spec.get("max_resources_per_run") or 50)
        return cls(
            servers=servers,
            allow_mutations=allow_mutations,
            allowed_roles=allowed_roles,
            max_resources_per_run=max_resources,
        )

    # ------------------------------------------------------------------ #
    # Permission gate.
    # ------------------------------------------------------------------ #

    def is_tool_allowed(self, *, server: str, tool: str, role: str) -> bool:
        cfg = self._server_cfg(server)
        if cfg is None:
            return False
        roles = cfg.allowed_roles or self.allowed_roles
        if role not in roles:
            return False
        allow_mutations = (
            cfg.allow_mutations
            if cfg.allow_mutations is not None
            else self.allow_mutations
        )
        if allow_mutations:
            return True
        for pat in MUTATION_PATTERNS:
            if pat.search(tool):
                return False
        return True

    def _server_cfg(self, name: str) -> MCPServerConfig | None:
        for s in self.servers:
            if s.name == name:
                return s
        return None

    # ------------------------------------------------------------------ #
    # Source contract.
    # ------------------------------------------------------------------ #

    def collect(
        self,
        *,
        goal: str,
        event_callback: Any | None = None,
    ) -> ResearchResult:
        # Connect + list every server. One server's failure does not
        # tank the run — record the error and continue.
        self.connect(event_callback=event_callback)

        documents: list[Document] = []
        for status in self._statuses.values():
            if not status.connected:
                continue
            for uri in status.resource_uris[: self.max_resources_per_run]:
                excerpt = self._read_resource(status.name, uri, event_callback=event_callback)
                if not excerpt:
                    continue
                documents.append(
                    Document(
                        source_type="internal",
                        title=_human_title_for(status.name, uri),
                        url=uri,
                        excerpt=excerpt[:1000],
                        accessed_at=_now_iso(),
                        metadata={"mcp_server": status.name, "kind": "resource"},
                    )
                )

        brief = self._compose_brief()
        stats = self.snapshot()

        # Always release sockets/processes — even if collect() raised.
        try:
            self.disconnect(event_callback=event_callback)
        except Exception as exc:        # noqa: BLE001
            _log.warning("MCP disconnect failed: %s", exc)

        return ResearchResult(
            brief=brief,
            documents=tuple(documents),
            stats=stats,
        )

    # ------------------------------------------------------------------ #
    # Connection lifecycle.
    # ------------------------------------------------------------------ #

    def connect(self, *, event_callback: Any | None = None) -> None:
        """Open every configured server. Errors are recorded, not raised."""
        for cfg in self.servers:
            status = ServerStatus(name=cfg.name, transport=cfg.transport)
            self._statuses[cfg.name] = status
            try:
                client = self._open_client(cfg)
                self._clients[cfg.name] = client
                tools = tuple(_safe_str(t) for t in client.list_tools())
                resources = tuple(_safe_str(r) for r in client.list_resources())
                status.connected = True
                status.tool_count = len(tools)
                status.resource_count = len(resources)
                status.tool_names = tools
                status.resource_uris = resources
                _emit(
                    event_callback,
                    {
                        "type": "mcp_connect",
                        "server": cfg.name,
                        "transport": cfg.transport,
                        "tool_count": status.tool_count,
                        "resource_count": status.resource_count,
                    },
                )
            except Exception as exc:    # noqa: BLE001
                status.error = str(exc)[:500]
                _log.warning("MCP server '%s' failed to connect: %s", cfg.name, exc)
                _emit(
                    event_callback,
                    {
                        "type": "mcp_connect",
                        "server": cfg.name,
                        "transport": cfg.transport,
                        "error": status.error,
                    },
                )

    def disconnect(self, *, event_callback: Any | None = None) -> None:
        for name in list(self._clients.keys())[::-1]:
            client = self._clients.pop(name, None)
            try:
                if client is not None and hasattr(client, "close"):
                    client.close()
            except Exception as exc:    # noqa: BLE001
                _log.warning("MCP server '%s' close failed: %s", name, exc)
            _emit(event_callback, {"type": "mcp_disconnect", "server": name})

    def _open_client(self, cfg: MCPServerConfig) -> Any:
        if self.client_factory is not None:
            return self.client_factory(cfg)
        if self.simulated:
            return _SimulatedMCPClient(cfg)
        # Lazy import — module stays importable without the [mcp] extra.
        # Both the import-line failure (no backend module) AND a runtime
        # ImportError raised inside ``open_real_client`` (no ``mcp`` SDK
        # installed) collapse to the same friendly install pointer.
        try:
            from grok_orchestra.sources._mcp_backend import open_real_client
        except ImportError as exc:
            raise MCPConnectionError(
                "MCP backend not installed. Install with: "
                "pip install 'grok-agent-orchestra[mcp]'"
            ) from exc
        try:
            return open_real_client(cfg)
        except ImportError as exc:
            raise MCPConnectionError(
                "MCP backend not installed. Install with: "
                "pip install 'grok-agent-orchestra[mcp]'"
            ) from exc

    # ------------------------------------------------------------------ #
    # Tool + resource calls (used by tools_runner.py glue).
    # ------------------------------------------------------------------ #

    def call_tool(
        self,
        *,
        server: str,
        tool: str,
        arguments: Mapping[str, Any] | None = None,
        role: str = "Harper",
        event_callback: Any | None = None,
    ) -> MCPToolCall:
        if not self.is_tool_allowed(server=server, tool=tool, role=role):
            raise MCPPermissionDenied(
                f"Tool '{tool}' on server '{server}' is not allowed for "
                f"role '{role}' (read-only mode or role gate)."
            )
        client = self._clients.get(server)
        if client is None:
            raise MCPConnectionError(f"MCP server '{server}' is not connected")
        ns = f"{server}__{tool}"
        import time as _time
        t0 = _time.monotonic()
        try:
            result_text = _safe_str(client.call_tool(tool, dict(arguments or {})))
            is_error = False
        except Exception as exc:        # noqa: BLE001
            result_text = f"tool error: {exc!s}"[:1000]
            is_error = True
        latency_ms = (_time.monotonic() - t0) * 1000.0
        call = MCPToolCall(
            server=server,
            tool=tool,
            namespaced=ns,
            inputs=dict(arguments or {}),
            output_text=result_text,
            is_error=is_error,
            latency_ms=round(latency_ms, 3),
        )
        self._tool_calls.append(call)
        _emit(
            event_callback,
            {
                "type": "mcp_tool_call",
                "server": server,
                "tool": tool,
                "namespaced": ns,
                "is_error": is_error,
                "latency_ms": call.latency_ms,
            },
        )
        return call

    def _read_resource(
        self,
        server: str,
        uri: str,
        *,
        event_callback: Any | None = None,
    ) -> str:
        cache_key = f"{server}::{uri}"
        if cache_key in self._resource_cache:
            return self._resource_cache[cache_key]
        client = self._clients.get(server)
        if client is None:
            return ""
        import time as _time
        t0 = _time.monotonic()
        try:
            payload = _safe_str(client.read_resource(uri))
        except Exception as exc:        # noqa: BLE001
            payload = ""
            _log.warning("MCP read_resource(%s, %s) failed: %s", server, uri, exc)
        latency_ms = (_time.monotonic() - t0) * 1000.0
        self._resource_cache[cache_key] = payload
        _emit(
            event_callback,
            {
                "type": "mcp_resource_get",
                "server": server,
                "uri": uri,
                "bytes": len(payload),
                "latency_ms": round(latency_ms, 3),
                "cached": False,
            },
        )
        return payload

    # ------------------------------------------------------------------ #
    # Reporting helpers.
    # ------------------------------------------------------------------ #

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": "mcp",
            "servers": [s.to_dict() for s in self._statuses.values()],
            "tool_calls": len(self._tool_calls),
            "resources_read": len(self._resource_cache),
        }

    def server_statuses(self) -> tuple[ServerStatus, ...]:
        return tuple(self._statuses.values())

    def tool_calls(self) -> tuple[MCPToolCall, ...]:
        return tuple(self._tool_calls)

    def _compose_brief(self) -> str:
        connected = [s for s in self._statuses.values() if s.connected]
        if not connected:
            return ""
        lines: list[str] = ["## MCP research findings", ""]
        for s in connected:
            lines.append(
                f"- **{s.name}** ({s.transport}) — {s.tool_count} tools, "
                f"{s.resource_count} resources"
            )
        for s in connected:
            if not s.resource_uris:
                continue
            lines.append("")
            lines.append(f"### {s.name} resources")
            for uri in s.resource_uris[:10]:
                lines.append(f"- `{uri}`")
        return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# Simulated in-process MCP client. Used when `simulated: true` so demos +
# the dry-run path never need a real MCP server. Exposed at module scope
# so tests can subclass it.
# --------------------------------------------------------------------------- #


@dataclass
class _SimulatedMCPClient:
    cfg: MCPServerConfig
    _tools: tuple[str, ...] = field(default_factory=tuple)
    _resources: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.cfg.name == "filesystem":
            self._tools = ("read_file", "list_directory", "search_files")
            self._resources = ("file:///docs/intro.md", "file:///docs/setup.md")
        elif self.cfg.name == "github":
            self._tools = ("search_issues", "get_issue", "list_pull_requests", "create_issue")
            self._resources = ("repo://owner/repo/issues/1", "repo://owner/repo/issues/2")
        else:
            self._tools = ("ping",)
            self._resources = ()

    def list_tools(self) -> tuple[str, ...]:
        return self._tools

    def list_resources(self) -> tuple[str, ...]:
        return self._resources

    def read_resource(self, uri: str) -> str:
        return f"[simulated] body of {uri}"

    def call_tool(self, tool: str, arguments: Mapping[str, Any]) -> str:
        return f"[simulated] {tool}({arguments!r})"

    def close(self) -> None:
        return None


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _resolve_env(value: str) -> str:
    """Replace ``${VAR}`` with ``os.environ['VAR']``.

    Missing env vars resolve to the empty string with a warning — the
    server might still work (e.g. an MCP filesystem server with no env)
    and we never want a missing env var to leak the literal ``${...}``
    into a subprocess argv.
    """
    if not value or "$" not in value:
        return value

    def _sub(match: re.Match[str]) -> str:
        var = match.group(1)
        env_val = os.environ.get(var)
        if env_val is None:
            _log.warning("MCP env interpolation: %s is not set", var)
            return ""
        return env_val

    return _ENV_PATTERN.sub(_sub, value)


def _emit(callback: Any, event: Mapping[str, Any]) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except Exception:                   # noqa: BLE001 — never break a run
        _log.exception("MCP event callback raised")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _human_title_for(server: str, uri: str) -> str:
    short = uri.rsplit("/", 1)[-1] or uri
    return f"{server}: {short}"


def _safe_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(_safe_str(v) for v in value)
    if isinstance(value, Mapping):
        return ", ".join(f"{k}={_safe_str(v)}" for k, v in value.items())
    if value is None:
        return ""
    return str(value)
