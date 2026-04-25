"""MCP YAML config parsing — env interpolation, validation, build_sources()."""

from __future__ import annotations

from typing import Any

import pytest

# --------------------------------------------------------------------------- #
# Env interpolation.
# --------------------------------------------------------------------------- #


def test_env_interpolation_resolves_at_parse_time(monkeypatch: pytest.MonkeyPatch) -> None:
    from grok_orchestra.sources.mcp_source import MCPServerConfig

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_abc123")
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    cfg = MCPServerConfig.from_dict({
        "name": "github",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github", "--db", "${DATABASE_URL}"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"},
    })
    assert cfg.env["GITHUB_PERSONAL_ACCESS_TOKEN"] == "ghp_abc123"
    assert "postgres://x" in cfg.args


def test_env_interpolation_missing_var_resolves_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from grok_orchestra.sources.mcp_source import MCPServerConfig

    monkeypatch.delenv("UNSET_VAR", raising=False)
    cfg = MCPServerConfig.from_dict({
        "name": "x",
        "transport": "stdio",
        "command": "x",
        "env": {"FOO": "${UNSET_VAR}"},
    })
    # Missing env vars resolve to empty — never leak the literal ${...}
    # into a subprocess argv.
    assert cfg.env["FOO"] == ""


def test_bearer_token_interpolation(monkeypatch: pytest.MonkeyPatch) -> None:
    from grok_orchestra.sources.mcp_source import MCPServerConfig

    monkeypatch.setenv("MY_MCP_TOKEN", "secret-xyz")
    cfg = MCPServerConfig.from_dict({
        "name": "internal",
        "transport": "http",
        "url": "https://my-mcp.example.com",
        "auth": {"type": "bearer", "token": "${MY_MCP_TOKEN}"},
    })
    assert cfg.auth_token == "secret-xyz"
    assert cfg.auth_type == "bearer"


# --------------------------------------------------------------------------- #
# Validation.
# --------------------------------------------------------------------------- #


def test_missing_name_raises() -> None:
    from grok_orchestra.sources import SourceError
    from grok_orchestra.sources.mcp_source import MCPServerConfig

    with pytest.raises(SourceError, match="missing 'name'"):
        MCPServerConfig.from_dict({"transport": "stdio", "command": "x"})


def test_unknown_transport_raises() -> None:
    from grok_orchestra.sources import SourceError
    from grok_orchestra.sources.mcp_source import MCPServerConfig

    with pytest.raises(SourceError, match="unknown transport"):
        MCPServerConfig.from_dict({"name": "x", "transport": "carrier-pigeon"})


def test_unknown_auth_type_raises() -> None:
    from grok_orchestra.sources import SourceError
    from grok_orchestra.sources.mcp_source import MCPServerConfig

    with pytest.raises(SourceError, match="unknown auth type"):
        MCPServerConfig.from_dict({
            "name": "x",
            "transport": "http",
            "auth": {"type": "oauth-magic"},
        })


def test_args_must_be_list() -> None:
    from grok_orchestra.sources import SourceError
    from grok_orchestra.sources.mcp_source import MCPServerConfig

    with pytest.raises(SourceError, match="must be a list"):
        MCPServerConfig.from_dict({
            "name": "x",
            "transport": "stdio",
            "command": "x",
            "args": "not-a-list",
        })


# --------------------------------------------------------------------------- #
# build_sources(): MCP source plugs in via the same registry as `web`.
# --------------------------------------------------------------------------- #


def test_build_sources_constructs_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    from grok_orchestra.sources import build_sources
    from grok_orchestra.sources.mcp_source import MCPSource

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_xyz")
    config: dict[str, Any] = {
        "sources": [
            {
                "type": "mcp",
                "servers": [
                    {
                        "name": "github",
                        "transport": "stdio",
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-github"],
                        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"},
                    }
                ],
                "allow_mutations": False,
                "allowed_roles": ["Harper", "Benjamin"],
            }
        ]
    }
    sources = build_sources(config)
    assert len(sources) == 1
    src = sources[0]
    assert isinstance(src, MCPSource)
    assert src.servers[0].name == "github"
    assert src.servers[0].env["GITHUB_PERSONAL_ACCESS_TOKEN"] == "ghp_xyz"
    assert src.allowed_roles == ("Harper", "Benjamin")


def test_build_sources_skips_invalid_mcp_block_without_killing_run(caplog) -> None:    # type: ignore[no-untyped-def]
    from grok_orchestra.sources import build_sources

    config = {
        "sources": [
            {"type": "mcp", "servers": []},                  # invalid (empty)
            {"type": "mcp", "servers": [{"name": "ok", "transport": "stdio"}]},
        ]
    }
    sources = build_sources(config)
    # The bad block was skipped; the good one came through.
    assert len(sources) == 1


def test_mixed_sources_web_and_mcp_coexist(monkeypatch: pytest.MonkeyPatch) -> None:
    from grok_orchestra.sources import build_sources

    monkeypatch.setenv("GH", "x")
    sources = build_sources({
        "sources": [
            {"type": "web"},
            {"type": "mcp", "servers": [{"name": "github", "transport": "stdio"}]},
        ]
    })
    kinds = {type(s).__name__ for s in sources}
    assert {"WebSource", "MCPSource"} <= kinds


def test_public_dict_strips_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    from grok_orchestra.sources.mcp_source import MCPServerConfig

    monkeypatch.setenv("GH_TOK", "ghp_supersecret")
    cfg = MCPServerConfig.from_dict({
        "name": "github",
        "transport": "stdio",
        "command": "npx",
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GH_TOK}"},
        "auth": {"type": "bearer", "token": "${GH_TOK}"},
    })
    pub = cfg.public_dict()
    blob = repr(pub)
    assert "ghp_supersecret" not in blob
    # The keys are surfaced — just not the values.
    assert pub["env_keys"] == ["GITHUB_PERSONAL_ACCESS_TOKEN"]
    assert pub["auth_type"] == "bearer"
