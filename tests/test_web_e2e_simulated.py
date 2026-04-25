"""Full simulated web research run end-to-end.

Covers two user-visible guarantees:

1. ``simulated: true`` lands canned web data into the goal + the run's
   citations list — no network, no API keys.
2. The publisher's report carries those citations under
   `## Citations` with an URL link.

Skips cleanly when ``[web]`` extras aren't installed.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("trafilatura")
pytest.importorskip("selectolax")


def _yaml(goal: str = "Weekly news digest on AI agents.") -> str:
    return f"""
name: web-e2e
goal: |
  {goal}
sources:
  - type: web
    provider: tavily
    max_results_per_query: 3
    blocked_domains:
      - pinterest.com
orchestra:
  mode: simulated
  agent_count: 4
  reasoning_effort: medium
  debate_rounds: 1
  orchestration:
    pattern: native
    config: {{}}
  agents:
    - {{name: Grok, role: coordinator}}
    - {{name: Harper, role: researcher}}
    - {{name: Benjamin, role: logician}}
    - {{name: Lucas, role: contrarian}}
safety:
  lucas_veto_enabled: true
  confidence_threshold: 0.5
deploy:
  target: stdout
"""


def _wait_for(client, run_id: str, *, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/runs/{run_id}").json()
        if body.get("status") in ("completed", "failed"):
            return body
        time.sleep(0.02)
    raise AssertionError("run did not finish in time")


def test_simulated_run_attaches_web_citations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROK_ORCHESTRA_WORKSPACE", str(tmp_path / "ws"))
    from fastapi.testclient import TestClient

    from grok_orchestra.web.main import create_app

    client = TestClient(create_app())
    run_id = client.post(
        "/api/run", json={"yaml": _yaml(), "simulated": True}
    ).json()["run_id"]
    body = _wait_for(client, run_id)
    assert body["status"] == "completed", body

    citations = body.get("citations") or []
    assert citations, "expected web citations to be attached to the run"
    assert all(c.get("source_type") == "web" for c in citations)
    assert all(c.get("url") for c in citations)
    # Source-stats budget snapshot is surfaced.
    stats = body.get("source_stats") or {}
    assert stats.get("max_searches") and stats.get("searches", 0) >= 1


def test_simulated_run_emits_web_search_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROK_ORCHESTRA_WORKSPACE", str(tmp_path / "ws"))
    from fastapi.testclient import TestClient

    from grok_orchestra.web.main import create_app

    client = TestClient(create_app())
    run_id = client.post(
        "/api/run", json={"yaml": _yaml(), "simulated": True}
    ).json()["run_id"]

    with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
        seen_types: list[str] = []
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            ev = ws.receive_json()
            t = ev.get("type")
            if t:
                seen_types.append(t)
            if t == "close":
                break
    assert "web_search_started" in seen_types
    assert "web_search_results" in seen_types


def test_report_md_includes_web_citations_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROK_ORCHESTRA_WORKSPACE", str(tmp_path / "ws"))
    from fastapi.testclient import TestClient

    from grok_orchestra.web.main import create_app

    client = TestClient(create_app())
    run_id = client.post(
        "/api/run", json={"yaml": _yaml(), "simulated": True}
    ).json()["run_id"]
    _wait_for(client, run_id)

    md = client.get(f"/api/runs/{run_id}/report.md").text
    assert "## Citations" in md
    # At least one of the canned URLs from the simulated catalogue lands
    # in the report.
    assert "example.org" in md.lower()


def test_runner_skips_sources_when_block_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No ``sources:`` in YAML ⇒ runner does nothing source-y; no citations."""
    monkeypatch.setenv("GROK_ORCHESTRA_WORKSPACE", str(tmp_path / "ws"))
    from fastapi.testclient import TestClient

    from grok_orchestra.web.main import create_app

    plain = """
name: plain
goal: hello
orchestra:
  mode: simulated
  agent_count: 4
  reasoning_effort: medium
  debate_rounds: 1
  orchestration: {pattern: native, config: {}}
  agents:
    - {name: Grok, role: coordinator}
    - {name: Harper, role: researcher}
    - {name: Benjamin, role: logician}
    - {name: Lucas, role: contrarian}
safety: {lucas_veto_enabled: true, confidence_threshold: 0.5}
deploy: {target: stdout}
"""
    client = TestClient(create_app())
    run_id = client.post(
        "/api/run", json={"yaml": plain, "simulated": True}
    ).json()["run_id"]
    body = _wait_for(client, run_id)
    assert body["status"] == "completed"
    assert body.get("citations") == []
    assert body.get("source_stats") == {}
