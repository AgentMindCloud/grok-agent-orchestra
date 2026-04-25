"""Full simulated-run lifecycle tests via /api/run + /api/runs/{id}.

Covers the chicken-and-egg case: ``POST /api/run`` returns immediately
with a run_id, and we have to poll ``GET /api/runs/{run_id}`` to wait
for the background task to finish.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from grok_orchestra.web.main import create_app  # noqa: E402

_YAML = """
name: simulated-run-test
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


def _wait_for(client: TestClient, run_id: str, *, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    delay = 0.01
    while time.monotonic() < deadline:
        r = client.get(f"/api/runs/{run_id}")
        if r.status_code == 200:
            body = r.json()
            if body["status"] in ("completed", "failed"):
                return body
        time.sleep(delay)
        delay = min(delay * 1.6, 0.2)
    pytest.fail(f"run {run_id!r} did not finish within {timeout}s")


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_post_run_returns_run_id(client: TestClient) -> None:
    r = client.post(
        "/api/run",
        json={"yaml": _YAML, "inputs": {}, "simulated": True},
    )
    assert r.status_code == 200
    assert "run_id" in r.json()


def test_post_run_then_poll_completes(client: TestClient) -> None:
    r = client.post(
        "/api/run",
        json={"yaml": _YAML, "inputs": {}, "simulated": True},
    )
    run_id = r.json()["run_id"]
    body = _wait_for(client, run_id)
    assert body["status"] == "completed", body
    assert body["final_output"], "expected final_output to be set"
    assert body["event_count"] > 0


def test_runs_list_includes_recent(client: TestClient) -> None:
    r = client.post(
        "/api/run",
        json={"yaml": _YAML, "inputs": {}, "simulated": True},
    )
    run_id = r.json()["run_id"]
    _wait_for(client, run_id)
    listing = client.get("/api/runs").json()
    assert any(item["id"] == run_id for item in listing["runs"])


def test_post_run_rejects_malformed_yaml(client: TestClient) -> None:
    r = client.post(
        "/api/run",
        json={"yaml": "name: x\norchestra: {agent_count: 7}", "simulated": True},
    )
    assert r.status_code == 400
