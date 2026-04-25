"""Model-string → client class resolver + per-run mode detection.

A model string is one of:

- ``"grok-4.20-0309"`` / ``"grok-4.20-multi-agent-0309"`` /
  ``"grok-2-latest"`` — anything starting with ``grok`` or ``xai/``
  routes to the GrokNativeClient.
- ``"openai/gpt-4o"`` / ``"anthropic/claude-3-5-sonnet"`` /
  ``"ollama/llama3.1"`` — the LiteLLM-style ``provider/model`` form
  routes to the LiteLLMClient.
- A YAML-defined alias, resolved through the ``model_aliases`` map.

This module is import-cheap: it does **not** import LiteLLM or
xai-sdk at module load. Concrete clients are constructed lazily.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "GROK_DEFAULT_MODEL",
    "detect_mode",
    "is_grok_model",
    "resolve_client",
    "resolve_role_models",
]


# Default Grok single-agent model. Kept in sync with
# ``runtime_simulated.SINGLE_AGENT_MODEL`` (single source of truth there).
GROK_DEFAULT_MODEL = "grok-4.20-0309"

# Matches "grok-…", "xai/…", "x-ai/…", "@xai/…" — every shape we ever
# see for an xAI-hosted model. Normalisation is intentionally
# permissive: we never mis-route a real Grok model to LiteLLM.
_GROK_PREFIXES = ("grok", "xai/", "x-ai/", "@xai/")


def is_grok_model(model: str | None) -> bool:
    if not model:
        return True              # "no model set" defaults to Grok-native
    m = model.strip().lower()
    return any(m.startswith(p) for p in _GROK_PREFIXES)


def resolve_alias(
    model: str | None,
    aliases: Mapping[str, str] | None,
) -> str | None:
    """Resolve a YAML alias → concrete model string. Idempotent."""
    if not model:
        return model
    if not aliases:
        return model
    seen: set[str] = set()
    cur = model
    while cur in aliases and cur not in seen:
        seen.add(cur)
        cur = aliases[cur]
    return cur


def resolve_client(
    model: str | None,
    *,
    aliases: Mapping[str, str] | None = None,
) -> Any:
    """Return an LLM client suitable for ``model``.

    Concrete client classes are lazy-imported so the search-only path
    doesn't pull in xai-sdk just to register a mock.
    """
    resolved = resolve_alias(model, aliases) or GROK_DEFAULT_MODEL
    if is_grok_model(resolved):
        from grok_orchestra.llm.grok import GrokNativeClient

        return GrokNativeClient(model=resolved)
    from grok_orchestra.llm.adapter import LiteLLMClient

    return LiteLLMClient(model=resolved)


def resolve_role_models(
    config: Mapping[str, Any],
    role_names: list[str],
) -> dict[str, str]:
    """Pin every named role to a concrete (alias-resolved) model.

    Override priority (highest wins):

    1. ``orchestra.agents[*].model``  — per-agent in the agents block.
    2. ``orchestra.roles.<name>.model`` — alternative per-role section
       (the YAML the user prompt sketches).
    3. Top-level ``model:`` — global default for the run.
    4. ``GROK_DEFAULT_MODEL`` — the framework fallback.

    Aliases are resolved at the end so users can declare a global
    ``"fast"`` alias and reference it anywhere.
    """
    aliases = config.get("model_aliases") or {}
    if not isinstance(aliases, Mapping):
        aliases = {}

    global_model: str | None = config.get("model")
    orch = config.get("orchestra") or {}
    if not isinstance(orch, Mapping):
        orch = {}

    per_agent: dict[str, str] = {}
    for entry in (orch.get("agents") or []):
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("name")
        model = entry.get("model")
        if name and model:
            per_agent[str(name)] = str(model)

    per_role: dict[str, str] = {}
    roles_block = orch.get("roles") or {}
    if isinstance(roles_block, Mapping):
        for key, body in roles_block.items():
            if isinstance(body, Mapping) and body.get("model"):
                per_role[str(key).lower()] = str(body["model"])

    out: dict[str, str] = {}
    for name in role_names:
        # Highest precedence: per-agent override.
        chosen = per_agent.get(name)
        # Then: per-role override (case-insensitive key match).
        if chosen is None:
            chosen = per_role.get(name.lower())
        # Then: global model.
        if chosen is None:
            chosen = global_model
        # Finally: framework default.
        chosen = resolve_alias(chosen, aliases) or GROK_DEFAULT_MODEL
        out[name] = chosen
    return out


def detect_mode(role_models: Mapping[str, str], *, pattern: str) -> str:
    """Label a run as ``native`` / ``simulated`` / ``adapter`` / ``mixed``.

    See module docstring on :mod:`grok_orchestra.llm` for the rules.
    """
    if not role_models:
        return "native" if pattern == "native" else "simulated"
    grok = [m for m in role_models.values() if is_grok_model(m)]
    other = [m for m in role_models.values() if not is_grok_model(m)]
    if not other:
        return "native" if pattern == "native" else "simulated"
    if not grok:
        return "adapter"
    return "mixed"
