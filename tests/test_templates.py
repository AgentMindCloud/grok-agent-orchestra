"""Validation + content tests for every bundled template.

These tests pin the catalog so we don't accidentally ship a template
that won't load, doesn't have a description, or breaks the
``grok-orchestra templates list`` snapshot.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from grok_orchestra import cli as cli_module
from grok_orchestra._templates import (
    Template,
    list_templates,
    render_template_yaml,
)
from grok_orchestra.parser import OrchestraConfigError, load_orchestra_yaml

runner = CliRunner()

# Tags the CLI's category grouping recognises. A template's first tag in
# this set drives its category bucket; a template with zero recognised
# tags lands in "other" — which is allowed but flagged below so we can
# audit it.
KNOWN_TAGS: frozenset[str] = frozenset(
    {
        "research",
        "business",
        "technical",
        "debate",
        "fast",
        "deep",
        "local-docs",
        "web-search",
    }
)


@pytest.fixture(scope="module")
def all_templates() -> list[Template]:
    return list_templates()


# --------------------------------------------------------------------------- #
# Existence / catalog shape.
# --------------------------------------------------------------------------- #


def test_at_least_eighteen_templates_ship(all_templates: list[Template]) -> None:
    """10 originals + 8 added in the templates-expansion session."""
    assert len(all_templates) >= 18, [t.name for t in all_templates]


def test_every_required_field_populated(all_templates: list[Template]) -> None:
    """Every template carries the metadata `templates list` and `show` need."""
    missing: list[str] = []
    for tpl in all_templates:
        if not tpl.name:
            missing.append(f"{tpl.path.name}: missing name")
        if not tpl.description:
            missing.append(f"{tpl.name}: missing description")
        if not tpl.version:
            missing.append(f"{tpl.name}: missing version")
        if not tpl.tags:
            missing.append(f"{tpl.name}: missing tags")
    assert not missing, "templates with missing metadata:\n  " + "\n  ".join(missing)


def test_every_template_has_at_least_one_known_tag(
    all_templates: list[Template],
) -> None:
    """Catches templates that would silently land in the 'Other' bucket."""
    untagged: list[str] = []
    for tpl in all_templates:
        if not (KNOWN_TAGS & set(tpl.tags)):
            untagged.append(f"{tpl.name} (tags={list(tpl.tags)})")
    assert not untagged, "templates with no recognised category tag:\n  " + "\n  ".join(
        untagged
    )


# --------------------------------------------------------------------------- #
# YAML-level validation.
# --------------------------------------------------------------------------- #


def test_every_template_parses_as_yaml(all_templates: list[Template]) -> None:
    for tpl in all_templates:
        body = tpl.path.read_text(encoding="utf-8")
        try:
            yaml.safe_load(body)
        except yaml.YAMLError as exc:
            pytest.fail(f"{tpl.name}: invalid YAML: {exc}")


def test_every_template_passes_schema_validation(
    all_templates: list[Template],
) -> None:
    """Every shipped template loads + validates via load_orchestra_yaml."""
    failures: list[str] = []
    for tpl in all_templates:
        try:
            load_orchestra_yaml(tpl.path)
        except OrchestraConfigError as exc:
            failures.append(f"{tpl.name}: {exc}")
    assert not failures, "schema validation failures:\n  " + "\n  ".join(failures)


def test_every_template_passes_validate_command(
    all_templates: list[Template],
) -> None:
    """The CLI ``validate`` command exits 0 against every shipped template."""
    failures: list[tuple[str, str]] = []
    for tpl in all_templates:
        result = runner.invoke(cli_module.app, ["validate", tpl.name])
        if result.exit_code != 0:
            failures.append((tpl.name, result.stdout))
    assert not failures, (
        "templates failing CLI validate:\n  "
        + "\n  ".join(f"{n}\n{out}" for n, out in failures)
    )


def test_render_template_yaml_returns_text(all_templates: list[Template]) -> None:
    for tpl in all_templates:
        text = render_template_yaml(tpl.name)
        assert text.strip(), f"{tpl.name}: empty YAML body"
        assert f"name: {tpl.name}" in text


# --------------------------------------------------------------------------- #
# `templates list` JSON output — stable shape ("snapshot" by structure).
# --------------------------------------------------------------------------- #


def _list_payload() -> dict:
    result = runner.invoke(
        cli_module.app, ["templates", "list", "--format", "json"]
    )
    assert result.exit_code == 0, result.stdout
    last = result.stdout.strip().splitlines()[-1]
    return json.loads(last)


def test_list_payload_has_expected_top_level_keys() -> None:
    payload = _list_payload()
    assert set(payload).issuperset({"ok", "count", "filter_tag", "templates"})
    assert payload["ok"] is True
    assert payload["count"] == len(payload["templates"])


def test_list_payload_template_record_shape() -> None:
    payload = _list_payload()
    assert payload["templates"], "no templates returned"
    rec = payload["templates"][0]
    expected_fields = {
        "name",
        "description",
        "version",
        "author",
        "tags",
        "mode",
        "pattern",
        "combined",
        "primary_category",
    }
    assert expected_fields.issubset(rec.keys())
    assert isinstance(rec["tags"], list)
    assert isinstance(rec["combined"], bool)


def test_list_payload_names_are_alphabetised_within_categories() -> None:
    payload = _list_payload()
    by_cat: dict[str, list[str]] = {}
    for rec in payload["templates"]:
        by_cat.setdefault(rec["primary_category"], []).append(rec["name"])
    for cat, names in by_cat.items():
        assert names == sorted(names), f"category {cat!r} not sorted: {names}"


# --------------------------------------------------------------------------- #
# Integration: copy + dry-run a template.
# --------------------------------------------------------------------------- #


def test_copy_then_validate_path(tmp_path: Path) -> None:
    dest = tmp_path / "my-spec.yaml"
    copy_result = runner.invoke(
        cli_module.app,
        ["templates", "copy", "red-team-the-plan", str(dest)],
    )
    assert copy_result.exit_code == 0, copy_result.stdout
    assert dest.exists()

    validate_result = runner.invoke(cli_module.app, ["validate", str(dest)])
    assert validate_result.exit_code == 0, validate_result.stdout
