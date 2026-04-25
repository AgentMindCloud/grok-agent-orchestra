"""HTTP-level tests for the FastAPI web app.

Skip cleanly when the [web] extras are not installed so a fresh
``pip install -e ".[dev]"`` (no [web]) can still run pytest.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from grok_orchestra import __version__  # noqa: E402
from grok_orchestra.web.main import create_app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


# --------------------------------------------------------------------------- #
# Static + health.
# --------------------------------------------------------------------------- #


def test_index_renders_dashboard_html(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Grok Agent Orchestra" in r.text
    # The bootstrap JSON must be embedded so the UI loads without a round trip.
    assert "id=\"bootstrap\"" in r.text
    assert "primary_category" in r.text


def test_health_returns_status(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


# --------------------------------------------------------------------------- #
# Templates API.
# --------------------------------------------------------------------------- #


def test_templates_list_matches_cli_count(client: TestClient) -> None:
    r = client.get("/api/templates")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["count"] == len(body["templates"])
    assert body["count"] >= 18


def test_templates_list_with_tag_filter(client: TestClient) -> None:
    r = client.get("/api/templates?tag=business")
    body = r.json()
    names = {t["name"] for t in body["templates"]}
    assert "competitive-analysis" in names
    assert "orchestra-native-4" not in names


def test_templates_show_returns_yaml_and_metadata(client: TestClient) -> None:
    r = client.get("/api/templates/red-team-the-plan")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "red-team-the-plan"
    assert "name: red-team-the-plan" in body["yaml"]
    assert body["mode"] == "simulated"
    assert body["pattern"] == "hierarchical"


def test_templates_show_404_for_unknown(client: TestClient) -> None:
    r = client.get("/api/templates/does-not-exist")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Validate.
# --------------------------------------------------------------------------- #


_VALID_YAML = """
name: web-test-spec
goal: Hello in 3 languages.
orchestra:
  mode: simulated
  agent_count: 4
  reasoning_effort: medium
  debate_rounds: 1
  orchestration:
    pattern: native
    config: {}
  agents:
    - {name: Grok,     role: coordinator}
    - {name: Harper,   role: researcher}
    - {name: Benjamin, role: logician}
    - {name: Lucas,    role: contrarian}
safety:
  lucas_veto_enabled: true
  confidence_threshold: 0.5
deploy:
  target: stdout
"""


def test_validate_happy_path(client: TestClient) -> None:
    r = client.post("/api/validate", json={"yaml": _VALID_YAML})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["mode"] == "simulated"
    assert body["pattern"] == "native"


def test_validate_rejects_malformed(client: TestClient) -> None:
    bad_yaml = "name: x\norchestra: {agent_count: 7}\n"  # 7 not in enum
    r = client.post("/api/validate", json={"yaml": bad_yaml})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "error" in body


# --------------------------------------------------------------------------- #
# Dry-run.
# --------------------------------------------------------------------------- #


def test_dry_run_returns_events_and_final(client: TestClient) -> None:
    r = client.post(
        "/api/dry-run",
        json={"yaml": _VALID_YAML, "inputs": {}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["events"], "expected non-empty event list"
    assert isinstance(body["final_content"], str)
    types = {e.get("type") for e in body["events"]}
    assert "run_started" in types
    assert "run_completed" in types
