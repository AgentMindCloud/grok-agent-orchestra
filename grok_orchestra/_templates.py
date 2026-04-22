"""Helpers for discovering and materialising bundled Orchestra templates.

Templates live in ``grok_orchestra/templates/`` and are shipped as
package data (see ``pyproject.toml``). Each is a YAML file that the
``templates`` and ``init`` CLI commands introspect.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "Template",
    "copy_template",
    "get_template",
    "list_templates",
]


_TEMPLATES_PACKAGE = "grok_orchestra.templates"


@dataclass(frozen=True)
class Template:
    """One bundled Orchestra template."""

    name: str  # filename stem, e.g. "basic-native"
    path: Path  # absolute path to the YAML on disk (when extracted)
    goal: str
    mode: str
    pattern: str
    combined: bool


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
        # Skip catalog / metadata files that live in the same directory.
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


def list_templates() -> list[Template]:
    """Return every bundled template, sorted by name.

    Each :class:`Template` carries enough metadata to render a quick
    table: ``mode``, ``pattern``, and whether the spec is a combined
    Bridge + Orchestra run.
    """
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
    # Accept `name.yaml` too for friendlier UX.
    if name.endswith((".yaml", ".yml")):
        stem = name.rsplit(".", 1)[0]
        if stem in candidates:
            return candidates[stem]
    raise FileNotFoundError(
        f"no template named {name!r}. Available: {sorted(candidates)}"
    )


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
