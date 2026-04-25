"""Orchestra spec parser — extends the Grok Build Bridge spec parser.

Bridge owns single-agent build spec parsing. Orchestra layers the multi-agent
``orchestra`` block and the extended ``safety`` fields on top. An Orchestra
spec is a strict superset of a Bridge spec: load_orchestra_yaml delegates the
Bridge pieces to :func:`grok_build_bridge.parser.load_yaml` and then validates
only the Orchestra additions against :mod:`orchestra.schema.json`.

All enum values and default values live in this module (as frozen dataclasses
and module-level constants) so schema and parser cannot drift.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from grok_build_bridge import _console
from grok_build_bridge.parser import BridgeConfigError
from grok_build_bridge.parser import load_yaml as bridge_load_yaml
from jsonschema import Draft202012Validator
from rich.panel import Panel
from rich.text import Text

# --------------------------------------------------------------------------- #
# Enum values (keep in sync with orchestra.schema.json).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class OrchestraEnums:
    """Canonical enum values shared by schema and parser."""

    modes: tuple[str, ...] = ("native", "simulated", "auto")
    efforts: tuple[str, ...] = ("low", "medium", "high", "xhigh")
    agent_counts: tuple[int, ...] = (4, 16)
    debate_styles: tuple[str, ...] = ("xai-native", "prompt-simulated")
    agent_names: tuple[str, ...] = ("Grok", "Harper", "Benjamin", "Lucas", "custom")
    agent_roles: tuple[str, ...] = (
        "coordinator",
        "researcher",
        "logician",
        "contrarian",
        "custom",
    )
    patterns: tuple[str, ...] = (
        "native",
        "hierarchical",
        "dynamic-spawn",
        "debate-loop",
        "parallel-tools",
        "recovery",
    )
    tools: tuple[str, ...] = ("x_search", "web_search", "code_execution")
    fallback_models: tuple[str, ...] = ("grok-4.20-0309",)
    lowered_efforts: tuple[str, ...] = ("low", "medium")
    lucas_models: tuple[str, ...] = ("grok-4.20-0309",)


ENUMS = OrchestraEnums()


# --------------------------------------------------------------------------- #
# Default values (keep in sync with orchestra.schema.json).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class OrchestraDefaults:
    """Canonical default values applied by :func:`apply_defaults`."""

    mode: str = "auto"
    reasoning_effort: str = "medium"
    include_verbose_streaming: bool = True
    use_encrypted_content: bool = False
    debate_rounds: int = 2

    # safety extension
    lucas_veto_enabled: bool = True
    lucas_model: str = "grok-4.20-0309"
    confidence_threshold: float = 0.75
    max_veto_retries: int = 1


DEFAULTS = OrchestraDefaults()


EFFORT_TO_AGENTS: Mapping[str, int] = MappingProxyType(
    {"low": 4, "medium": 4, "high": 16, "xhigh": 16}
)


# --------------------------------------------------------------------------- #
# Error type.
# --------------------------------------------------------------------------- #


class OrchestraConfigError(BridgeConfigError):
    """Raised for invalid Orchestra spec data.

    Subclasses Bridge's config error so callers handling Bridge failures also
    catch Orchestra failures. Carries an optional ``key_path`` pointing at the
    exact JSON path of the offending field so the CLI can surface a precise
    Rich error.
    """

    def __init__(self, message: str, *, key_path: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.key_path = key_path

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.key_path:
            return f"{self.message} (at {self.key_path})"
        return self.message

    def render(self, console: Any | None = None) -> None:
        """Render this error to the shared Rich console."""
        target = console if console is not None else _console.console
        body = Text()
        body.append("Orchestra config error\n\n", style="bold red")
        body.append(self.message, style="white")
        if self.key_path:
            body.append("\n\nat: ", style="dim")
            body.append(self.key_path, style="bold yellow")
        target.print(Panel(body, border_style="red", title="grok-orchestra"))


# --------------------------------------------------------------------------- #
# Schema loading.
# --------------------------------------------------------------------------- #

_SCHEMA_PATH = Path(__file__).parent / "schema" / "orchestra.schema.json"


def _load_schema() -> dict[str, Any]:
    with _SCHEMA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _format_key_path(absolute_path: Any) -> str:
    parts: list[str] = []
    for token in absolute_path:
        if isinstance(token, int):
            parts.append(f"[{token}]")
        elif parts:
            parts.append(f".{token}")
        else:
            parts.append(str(token))
    return "".join(parts) or "<root>"


# --------------------------------------------------------------------------- #
# Public API.
# --------------------------------------------------------------------------- #


def map_effort_to_agents(effort: str) -> int:
    """Map a ``reasoning_effort`` string to an ``agent_count`` value.

    Low/medium map to 4, high/xhigh map to 16 (per Grok 4.20's multi-agent
    model sizing guidance).
    """
    try:
        return EFFORT_TO_AGENTS[effort]
    except KeyError as exc:
        raise OrchestraConfigError(
            f"Unknown reasoning_effort: {effort!r}. "
            f"Expected one of {list(ENUMS.efforts)}.",
            key_path="orchestra.reasoning_effort",
        ) from exc


def resolve_mode(config: Mapping[str, Any]) -> str:
    """Resolve the effective execution mode for ``config``.

    Handles the ``auto`` case: returns ``"native"`` if an ``agent_count`` is
    set AND ``include_verbose_streaming`` is enabled (the combination the
    native multi-agent endpoint expects); otherwise returns ``"simulated"``.
    """
    orch = config.get("orchestra", {}) or {}
    mode = orch.get("mode", DEFAULTS.mode)
    if mode in ("native", "simulated"):
        return mode
    if mode != "auto":
        raise OrchestraConfigError(
            f"Unknown orchestra.mode: {mode!r}. "
            f"Expected one of {list(ENUMS.modes)}.",
            key_path="orchestra.mode",
        )
    agent_count = orch.get("agent_count")
    verbose = orch.get("include_verbose_streaming", DEFAULTS.include_verbose_streaming)
    if agent_count and verbose:
        return "native"
    return "simulated"


def apply_defaults(config: dict[str, Any]) -> dict[str, Any]:
    """Apply Orchestra-level defaults to ``config`` in place and return it.

    - Fills in orchestra defaults (mode, reasoning_effort, streaming, etc.).
    - Derives ``agent_count`` from ``reasoning_effort`` when not specified.
    - Fills in safety-extension defaults.
    """
    orch = config.setdefault("orchestra", {})
    orch.setdefault("mode", DEFAULTS.mode)
    orch.setdefault("reasoning_effort", DEFAULTS.reasoning_effort)
    orch.setdefault("include_verbose_streaming", DEFAULTS.include_verbose_streaming)
    orch.setdefault("use_encrypted_content", DEFAULTS.use_encrypted_content)
    orch.setdefault("debate_rounds", DEFAULTS.debate_rounds)
    if "agent_count" not in orch:
        orch["agent_count"] = map_effort_to_agents(orch["reasoning_effort"])

    safety = config.setdefault("safety", {})
    safety.setdefault("lucas_veto_enabled", DEFAULTS.lucas_veto_enabled)
    safety.setdefault("lucas_model", DEFAULTS.lucas_model)
    safety.setdefault("confidence_threshold", DEFAULTS.confidence_threshold)
    safety.setdefault("max_veto_retries", DEFAULTS.max_veto_retries)
    return config


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def validate(config: Mapping[str, Any]) -> None:
    """Validate ``config`` against the Orchestra extensions schema.

    Raises :class:`OrchestraConfigError` on the first failure, pointing at the
    exact key path of the offending value.
    """
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(config), key=lambda e: list(e.absolute_path))
    if not errors:
        return
    first = errors[0]
    key_path = _format_key_path(first.absolute_path)
    raise OrchestraConfigError(first.message, key_path=key_path)


def parse(source: str | dict[str, Any]) -> Mapping[str, Any]:
    """Parse an Orchestra spec from a raw YAML string or an in-memory dict.

    Bridge's schema is not re-run here (callers who need Bridge validation
    should use :func:`load_orchestra_yaml`); this helper is for unit tests and
    notebook-driven flows.
    """
    if isinstance(source, dict):
        raw = dict(source)
    else:
        import yaml

        try:
            loaded = yaml.safe_load(source)
        except yaml.YAMLError as exc:
            raise OrchestraConfigError(f"Could not parse YAML: {exc}") from exc
        if not isinstance(loaded, dict):
            raise OrchestraConfigError("Spec root must be a mapping.")
        raw = loaded

    validate(raw)
    apply_defaults(raw)
    return _freeze(raw)


def load_orchestra_yaml(path: str | Path) -> Mapping[str, Any]:
    """Load and fully validate an Orchestra YAML spec from disk.

    Parsing flow:
    - Read the file with ``yaml.safe_load`` (so Orchestra-only fields like
      ``goal``, ``orchestra``, ``tags``, ``description``, ``inputs`` …
      are accepted without colliding with Bridge's strict
      ``additionalProperties: false`` schema).
    - When ``combined: true`` is set, *also* run Bridge's full validator —
      combined runs have a real ``build:`` block that needs Bridge's
      schema applied.
    - Validate the Orchestra additions against
      :mod:`grok_orchestra.schema.orchestra.schema.json`.
    - Apply defaults and freeze.

    The returned mapping is frozen (``MappingProxyType`` all the way down)
    so downstream code can treat the spec as immutable.
    """
    import yaml

    text = Path(path).read_text(encoding="utf-8")
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise OrchestraConfigError(f"Could not parse YAML at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise OrchestraConfigError(
            f"Spec root must be a mapping, got {type(raw).__name__}."
        )

    if raw.get("combined") is True:
        # Bridge owns the build half — run its validator so the build:
        # block is checked against Bridge's own schema. Bridge's load_yaml
        # re-reads the file, which is fine for combined specs.
        bridge_load_yaml(str(path))

    validate(raw)
    apply_defaults(raw)
    return _freeze(raw)
