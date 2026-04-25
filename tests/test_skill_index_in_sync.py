"""Skill catalogue stays in lockstep with the upstream INDEX.

The skill ships ``skills/agent-orchestra/templates/INDEX.{yaml,json}``
as a static copy of ``grok_orchestra/templates/INDEX.yaml`` so the
``choose_template.py`` script needs no `pyyaml` dep at install time.
This test fails fast if either copy drifts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO = Path(__file__).resolve().parent.parent
_UPSTREAM = _REPO / "grok_orchestra" / "templates" / "INDEX.yaml"
_BUNDLED_YAML = _REPO / "skills" / "agent-orchestra" / "templates" / "INDEX.yaml"
_BUNDLED_JSON = _REPO / "skills" / "agent-orchestra" / "templates" / "INDEX.json"


def test_bundled_yaml_is_byte_equivalent_to_upstream() -> None:
    assert _BUNDLED_YAML.exists()
    assert _UPSTREAM.exists()
    assert _BUNDLED_YAML.read_bytes() == _UPSTREAM.read_bytes(), (
        "skills/agent-orchestra/templates/INDEX.yaml has drifted from "
        "grok_orchestra/templates/INDEX.yaml. Re-run the sync command in "
        "skills/agent-orchestra/templates/README.md."
    )


def test_bundled_json_matches_yaml_content() -> None:
    assert _BUNDLED_JSON.exists()
    yaml_data = yaml.safe_load(_BUNDLED_YAML.read_text(encoding="utf-8"))
    json_data = json.loads(_BUNDLED_JSON.read_text(encoding="utf-8"))
    assert yaml_data == json_data, (
        "INDEX.json semantic drift from INDEX.yaml — re-run the sync."
    )


def test_every_template_has_required_fields() -> None:
    """Locks the schema choose_template.py expects."""
    data = json.loads(_BUNDLED_JSON.read_text(encoding="utf-8"))
    required = {"slug", "name", "description", "categories", "estimated_tokens", "mode", "pattern"}
    for tpl in data["templates"]:
        assert required <= tpl.keys(), f"missing fields on {tpl.get('slug')!r}"
