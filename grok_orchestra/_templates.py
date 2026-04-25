"""Helpers for discovering and materialising bundled Orchestra templates.

Templates live in ``grok_orchestra/templates/`` and are shipped as
package data (see ``pyproject.toml``). Each is a YAML file that the
``templates`` and ``init`` CLI commands introspect.

A template's top-level YAML may carry these *display-only* metadata
fields in addition to the schema-required `name`, `goal`, `orchestra`:

    description     one-line human summary
    version         template version string (defaults to "1.0.0")
    author          person/team who maintains it
    tags            list of tag strings (e.g. ["research", "deep"])

These are surfaced by the ``templates list`` / ``templates show``
commands and ignored by the runtime. The runtime spec schema sets
``additionalProperties: true`` at the root so unknown top-level fields
neither reach the executor nor cause validation failures.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "Template",
    "copy_template",
    "get_template",
    "list_templates",
    "render_template_yaml",
    "templates_json_payload",
]


_TEMPLATES_PACKAGE = "grok_orchestra.templates"


@dataclass(frozen=True)
class Template:
    """One bundled Orchestra template."""

    name: str  # filename stem, e.g. "deep-research-hierarchical"
    path: Path  # absolute path to the YAML on disk (when extracted)
    goal: str
    mode: str
    pattern: str
    combined: bool
    description: str = ""
    version: str = "1.0.0"
    author: str = "AgentMindCloud"
    tags: tuple[str, ...] = field(default_factory=tuple)


_NON_TEMPLATE_STEMS: frozenset[str] = frozenset({"INDEX", "index"})


def _iter_yaml_names() -> Iterator[str]:
    try:
        pkg = resources.files(_TEMPLATES_PACKAGE)
    except (ModuleNotFoundError, FileNotFoundError):
        return
    for item in pkg.iterdir():  # type: ignore[attr-defined]
        name = item.name
        if not (name.endswith(".yaml") or name.endswith(".yml")):
            continue
        stem = name.rsplit(".", 1)[0]
        if stem in _NON_TEMPLATE_STEMS or stem.startswith("."):
            continue
        yield name


def _read_yaml(name: str) -> tuple[str, dict[str, Any]]:
    pkg = resources.files(_TEMPLATES_PACKAGE)
    with resources.as_file(pkg / name) as path:  # type: ignore[arg-type]
        text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        data = {}
    return text, data


def _coerce_tags(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip().lower())
    return tuple(out)


def list_templates() -> list[Template]:
    """Return every bundled template, sorted by name."""
    out: list[Template] = []
    for name in sorted(_iter_yaml_names()):
        stem = name.rsplit(".", 1)[0]
        _text, data = _read_yaml(name)
        orch = data.get("orchestra", {}) or {}
        orchestration = orch.get("orchestration", {}) or {}
        pkg = resources.files(_TEMPLATES_PACKAGE)
        with resources.as_file(pkg / name) as path:  # type: ignore[arg-type]
            abs_path = Path(path)
        out.append(
            Template(
                name=stem,
                path=abs_path,
                goal=str(data.get("goal", "")),
                mode=str(orch.get("mode", "auto")),
                pattern=str(orchestration.get("pattern", "native")),
                combined=bool(data.get("combined", False)),
                description=str(data.get("description", "")),
                version=str(data.get("version", "1.0.0")),
                author=str(data.get("author", "AgentMindCloud")),
                tags=_coerce_tags(data.get("tags")),
            )
        )
    return out


def get_template(name: str) -> Template:
    """Look up a template by name (without extension).

    Raises :class:`FileNotFoundError` when ``name`` does not match any
    bundled template.
    """
    candidates = {tpl.name: tpl for tpl in list_templates()}
    if name in candidates:
        return candidates[name]
    if name.endswith((".yaml", ".yml")):
        stem = name.rsplit(".", 1)[0]
        if stem in candidates:
            return candidates[stem]
    raise FileNotFoundError(
        f"no template named {name!r}. Available: {sorted(candidates)}"
    )


def render_template_yaml(name: str) -> str:
    """Return the raw YAML text of template ``name``.

    Raises :class:`FileNotFoundError` when ``name`` does not match any
    bundled template. Used by ``grok-orchestra templates show``.
    """
    template = get_template(name)
    return template.path.read_text(encoding="utf-8")


def templates_json_payload(
    *,
    tag: str | None = None,
    primary_category: Callable[[Template], str] | None = None,
) -> dict[str, Any]:
    """Return the JSON-serialisable payload `templates list --format json` emits.

    The CLI (`_do_list` in ``grok_orchestra.cli``) and the web layer
    (``GET /api/templates``) both call this so they cannot drift on
    field names or filtering semantics.

    ``primary_category`` is injected by the caller because the
    category-bucket ordering lives in the CLI. We default to a no-op
    when called outside the CLI (e.g. from web tests that don't care
    about the bucket label).
    """
    selected = list_templates()
    if tag:
        needle = tag.strip().lower()
        selected = [t for t in selected if needle in t.tags]

    def _category(t: Template) -> str:
        return primary_category(t) if primary_category else "other"

    return {
        "ok": True,
        "count": len(selected),
        "filter_tag": tag,
        "templates": [
            {
                "name": t.name,
                "description": t.description,
                "version": t.version,
                "author": t.author,
                "tags": list(t.tags),
                "mode": t.mode,
                "pattern": t.pattern,
                "combined": t.combined,
                "primary_category": _category(t),
            }
            for t in selected
        ],
    }


def copy_template(name: str, out_path: str | Path) -> Path:
    """Copy template ``name`` to ``out_path``. Returns the resolved destination.

    If ``out_path`` already exists, :class:`FileExistsError` is raised so
    callers can surface an actionable message (the CLI does).
    """
    template = get_template(name)
    destination = Path(out_path)
    if destination.is_dir():
        destination = destination / f"{template.name}.yaml"
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite {destination}. Delete it or pass a different --out."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        template.path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return destination
