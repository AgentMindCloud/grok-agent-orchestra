"""Optional shared-password auth — backend behaviour matrix.

Off (no env var): every endpoint open. ``/api/auth/status`` reports
``required: false`` so the frontend can skip the login UI.

On (env var set):
- ``GET /api/health`` and ``GET /api/templates`` stay open (cheap;
  the login page needs to render before there's a session).
- ``POST /api/run`` returns 401 without a session and 200 with
  the cookie or the ``Authorization: Bearer <password>`` header.
- ``POST /api/auth/login`` accepts the password and sets the
  ``__orchestra_session`` cookie.
"""

from __future__ import annotations

import pytest

httpx = pytest.importorskip("httpx")
fastapi_testclient = pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402

YAML = "name: t\ngoal: hi\norchestra:\n  mode: simulated\n  agent_count: 4\n  reasoning_effort: low\n  debate_rounds: 1\n  orchestration: {pattern: native, config: {}}\n  agents:\n    - {name: Grok, role: coordinator}\n    - {name: Harper, role: researcher}\n    - {name: Benjamin, role: logician}\n    - {name: Lucas, role: contrarian}\nsafety: {lucas_veto_enabled: true, confidence_threshold: 0.5}\ndeploy: {target: stdout}\n"


def _client() -> TestClient:
    from grok_orchestra.web.main import create_app

    return TestClient(create_app())


# --------------------------------------------------------------------------- #
# Off-by-default.
# --------------------------------------------------------------------------- #


def test_status_reports_disabled_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROK_ORCHESTRA_AUTH_PASSWORD", raising=False)
    with _client() as c:
        r = c.get("/api/auth/status")
        assert r.status_code == 200
        assert r.json() == {"required": False, "authenticated": True}


def test_run_endpoint_open_when_auth_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROK_ORCHESTRA_AUTH_PASSWORD", raising=False)
    with _client() as c:
        r = c.post("/api/run", json={"yaml": YAML, "simulated": True})
        # 200 (run accepted) or 400 (yaml rejected) — but never 401.
        assert r.status_code != 401


# --------------------------------------------------------------------------- #
# On.
# --------------------------------------------------------------------------- #


def test_run_endpoint_requires_session_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROK_ORCHESTRA_AUTH_PASSWORD", "hunter2")
    with _client() as c:
        r = c.post("/api/run", json={"yaml": YAML, "simulated": True})
        assert r.status_code == 401


def test_login_sets_cookie_and_unlocks_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROK_ORCHESTRA_AUTH_PASSWORD", "hunter2")
    with _client() as c:
        r = c.post("/api/auth/login", json={"password": "wrong"})
        assert r.status_code == 401

        r = c.post("/api/auth/login", json={"password": "hunter2"})
        assert r.status_code == 200
        # Cookie is now part of the TestClient session.
        r2 = c.post("/api/run", json={"yaml": YAML, "simulated": True})
        assert r2.status_code != 401


def test_bearer_header_unlocks_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROK_ORCHESTRA_AUTH_PASSWORD", "hunter2")
    with _client() as c:
        r = c.post(
            "/api/run",
            json={"yaml": YAML, "simulated": True},
            headers={"Authorization": "Bearer hunter2"},
        )
        assert r.status_code != 401


def test_health_stays_open_under_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROK_ORCHESTRA_AUTH_PASSWORD", "hunter2")
    with _client() as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/templates").status_code == 200


def test_status_reports_required_under_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROK_ORCHESTRA_AUTH_PASSWORD", "hunter2")
    with _client() as c:
        r = c.get("/api/auth/status")
        body = r.json()
        assert body["required"] is True
        assert body["authenticated"] is False


# --------------------------------------------------------------------------- #
# /api/dry-run + /api/validate must follow the same gate as /api/run —
# anonymous quota-burn through dry-run was the original gap.
# --------------------------------------------------------------------------- #


def test_dry_run_requires_session_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROK_ORCHESTRA_AUTH_PASSWORD", "hunter2")
    with _client() as c:
        r = c.post("/api/dry-run", json={"yaml": YAML})
        assert r.status_code == 401


def test_dry_run_open_when_auth_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROK_ORCHESTRA_AUTH_PASSWORD", raising=False)
    with _client() as c:
        r = c.post("/api/dry-run", json={"yaml": YAML})
        # 200 (dry-run completed) or 400 (yaml rejected) — but never 401.
        assert r.status_code != 401


def test_validate_requires_session_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROK_ORCHESTRA_AUTH_PASSWORD", "hunter2")
    with _client() as c:
        r = c.post("/api/validate", json={"yaml": YAML})
        assert r.status_code == 401


def test_validate_open_when_auth_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROK_ORCHESTRA_AUTH_PASSWORD", raising=False)
    with _client() as c:
        r = c.post("/api/validate", json={"yaml": YAML})
        assert r.status_code != 401
