# MCP — Model Context Protocol

Connect Harper to your private GitHub repo, internal docs, Postgres
instance, Slack history, or any other [Model Context Protocol](https://modelcontextprotocol.io/)
server. MCPSource is a peer to [`web_search`](web-search.md) and
[`local_docs`](local-docs.md): one Source interface, three concrete
backends.

## Setup

```bash
pip install "grok-agent-orchestra[mcp]"
# Anything you'd point Claude Desktop or Cursor at also works here.
```

The framework reads the `mcp` SDK's own env vars; no custom
credential paths.

## YAML

```yaml
sources:
  - type: mcp
    allow_mutations: false              # default; blocks write/delete/exec tool patterns
    allowed_roles: [Harper]             # which roles may call MCP tools
    max_resources_per_run: 50

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
```

## Transports

| Transport | Use it for |
| --- | --- |
| `stdio` | Locally-spawned servers (the official `@modelcontextprotocol/server-*` packages). |
| `http` | Remote MCP servers. Bearer token via `auth:`. |
| `websocket` | Long-lived sessions (rare; use `http` unless your server requires WS). |

## Tool naming

Every tool exported by an MCP server is namespaced as
`<server-name>__<tool-name>` so multi-server runs can't collide:

```
github__search_issues
github__list_pull_requests
postgres__query
filesystem__read_file
```

## Permission gates

Two gates run before every tool call:

1. **Role gate.** The role calling the tool must be in
   `allowed_roles` (or in the per-server `allowed_roles` override).
   Default: `[Harper]`.
2. **Read-only gate.** Tool names matching common mutation tokens
   (`write`, `create`, `update`, `delete`, `exec`, …) are blocked
   unless `allow_mutations: true` on the source or the per-server
   override.

Per-server overrides win:

```yaml
sources:
  - type: mcp
    allow_mutations: false
    servers:
      - name: github                  # read-only — blocks create_issue
        transport: stdio
        command: npx
        args: ["-y", "@modelcontextprotocol/server-github"]
      - name: scratch-postgres        # explicitly opted-in for writes
        transport: stdio
        command: npx
        args: ["-y", "@modelcontextprotocol/server-postgres", "${DATABASE_URL}"]
        allow_mutations: true
```

A blocked call surfaces as `MCPPermissionDenied` and (in iterative
patterns) feeds the next round's Lucas evaluation.

## Caching

- **Resources** are cached per-run by `<server>::<uri>`. Multi-role
  references to the same MCP doc cost one read.
- **Tool calls** are *not* cached — they're side-effecting in the
  general case, even if the specific tool happens to be a pure read.

## Tracing

Three reserved `SpanKind` values fire when MCP is active:

| Span | Attributes |
| --- | --- |
| `mcp_connect` | `server`, `transport`, `tool_count`, `resource_count` |
| `mcp_tool_call` | `server`, `tool`, `namespaced`, `is_error`, `latency_ms` |
| `mcp_resource_get` | `server`, `uri`, `bytes`, `latency_ms`, `cached` |

Span attributes intentionally exclude tool arguments and resource
bodies — those can carry secrets. Outputs are surfaced to the LLM,
not the tracer.

## Security model

- **Secrets stay on the host.** `${VAR}` interpolation happens at
  YAML parse time. Resolved values flow to the subprocess (stdio) or
  HTTP client only — never into Documents, briefs, span attributes,
  or LLM prompts.
- **One-server failure ≠ run failure.** If a server can't connect or
  list its surfaces, the error is recorded on its `ServerStatus` and
  the rest of the run proceeds.
- **Lucas still vetoes.** Tool results land in the synthesis;
  Lucas's strict-JSON pass evaluates the final output the same way
  as for any other Source.

## Multi-server runs

Multi-server is the common case. The brief lists every connected
server with its tool count + first 10 resources, so Harper picks
which side of the house to query before invoking namespaced tools.

```yaml
sources:
  - type: mcp
    servers:
      - name: github                  # repo + issues
        transport: stdio
        command: npx
        args: ["-y", "@modelcontextprotocol/server-github"]
        env: {GITHUB_PERSONAL_ACCESS_TOKEN: ${GITHUB_TOKEN}}
      - name: filesystem              # local docs folder
        transport: stdio
        command: npx
        args: ["-y", "@modelcontextprotocol/server-filesystem", "./docs"]
```

## Examples

- [`examples/mcp-github/spec.yaml`](https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/examples/mcp-github/spec.yaml)
  — Harper summarises the 5 most recent open issues on a public repo.
- [`examples/mcp-filesystem/spec.yaml`](https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/examples/mcp-filesystem/spec.yaml)
  — Read a local docs folder via MCP filesystem (alternative to
  `LocalDocsSource` for users with an existing MCP setup).

## See also

- [Local docs](local-docs.md) — the offline-first alternative.
- [Web search](web-search.md) — the public-web alternative.
- [Architecture → Extending](../architecture/extending.md) — adding a
  new transport or replacing the read-only gate.
