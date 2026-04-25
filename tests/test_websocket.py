"""WebSocket event-streaming tests.

These run the run-lifecycle through ``TestClient.websocket_connect`` and
assert the snapshot-then-tail contract. Skip cleanly when ``[web]`` is
not installed.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from grok_orchestra.web.main import create_app

_YAML = """
name: ws-test
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


def _drain(ws, *, terminal: set[str], timeout: float = 5.0) -> list[dict]:
    events: list[dict] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ev = ws.receive_json()
        events.append(ev)
        if ev.get("type") in terminal:
            return events
    raise AssertionError(
        f"timed out waiting for one of {terminal}; got types="
        f"{[e.get('type') for e in events]}"
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _wait_for_status(client: TestClient, run_id: str, target: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/runs/{run_id}").json()
        if body.get("status") in (target, "completed", "failed"):
            return
        time.sleep(0.02)
    raise AssertionError(f"run {run_id!r} never reached status {target!r}")


def test_websocket_streams_snapshot_then_close(client: TestClient) -> None:
    r = client.post(
        "/api/run",
        json={"yaml": _YAML, "inputs": {}, "simulated": True},
    )
    run_id = r.json()["run_id"]

    with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
        events = _drain(ws, terminal={"close"})

    types = [e.get("type") for e in events]
    assert types[0] == "snapshot_begin"
    assert "snapshot_end" in types
    assert "close" in types


def test_websocket_late_connect_replays_buffered_events(client: TestClient) -> None:
    """Connect *after* the run has completed — buffer alone delivers events."""
    r = client.post(
        "/api/run",
        json={"yaml": _YAML, "inputs": {}, "simulated": True},
    )
    run_id = r.json()["run_id"]

    # Wait for completion so the buffer is fully populated.
    _wait_for_status(client, run_id, "completed")

    with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
        events = _drain(ws, terminal={"close"})

    types = [e.get("type") for e in events]
    assert types[0] == "snapshot_begin"
    # Lifecycle events from the run must be in the replay buffer.
    assert "run_started" in types
    assert "run_completed" in types
    assert types[-1] == "close"


def test_websocket_run_completed_implies_final_output(client: TestClient) -> None:
    r = client.post(
        "/api/run",
        json={"yaml": _YAML, "inputs": {}, "simulated": True},
    )
    run_id = r.json()["run_id"]

    with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
        events = _drain(ws, terminal={"close"})

    completed = [e for e in events if e.get("type") == "run_completed"]
    assert completed, "no run_completed event seen"
    assert completed[0].get("final_output"), "run_completed missing final_output"


def test_websocket_unknown_run_id_closes_with_error(client: TestClient) -> None:
    with client.websocket_connect("/ws/runs/does-not-exist") as ws:
        first = ws.receive_json()
    assert first.get("type") == "error"
