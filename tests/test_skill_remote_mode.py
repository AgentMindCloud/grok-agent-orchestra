"""SKILL: remote_run.py — POST + poll loop, fully mocked urllib.

Patches ``urllib.request.urlopen`` at the module the script uses.
A tiny scripted handler responds to each URL the script touches:
``POST /api/run`` returns a run_id; one or more ``GET
/api/runs/{id}`` calls return ``running`` then ``completed``;
``GET /api/runs/{id}/report.md`` returns the rendered Markdown.

We reuse the import path from the local-mode test (importlib.util)
so neither test depends on the skill being on PYTHONPATH.
"""

from __future__ import annotations

import importlib.util
import io
import json
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "skills" / "agent-orchestra" / "scripts" / "remote_run.py"


@pytest.fixture(scope="module")
def remote_module():
    spec = importlib.util.spec_from_file_location("remote_run", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# Tiny urllib.request.urlopen stub.
# --------------------------------------------------------------------------- #


class _FakeResp:
    def __init__(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.status = status
        self._body = body
        self.headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return self._body

    def __enter__(self):                                              # noqa: D401
        return self

    def __exit__(self, *_exc):                                        # noqa: D401
        return False


class _Handler:
    """Per-test scripted responder."""

    def __init__(self, script: list[tuple[str, _FakeResp]]) -> None:
        # Each entry is (url-suffix-match, response). Consumed in order
        # so a sequence of GETs to the same URL can drive a polling test.
        self.script = list(script)
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def __call__(self, req, timeout: float | None = None):           # noqa: ANN001
        url = req.full_url
        method = req.get_method()
        headers = {k: v for k, v in req.header_items()}
        self.calls.append((method, url, headers))
        for suffix, resp in self.script:
            if suffix in url:
                self.script = [(s, r) for (s, r) in self.script if s != suffix or r is not resp]
                # Re-add with same suffix if the next response also targets it
                # (handled by the explicit append-to-end below in the polling test).
                return resp
        raise AssertionError(f"unscripted request: {method} {url}")


def _invoke(remote_module, argv, env: dict[str, str], **patches):    # noqa: ANN001
    buf = io.StringIO()
    with patch.dict("os.environ", env, clear=False):
        with patch("urllib.request.urlopen", **patches):
            with redirect_stdout(buf):
                rc = remote_module.main(argv)
    last = buf.getvalue().strip().splitlines()[-1]
    payload = last[len("RESULT_JSON: "):] if last.startswith("RESULT_JSON: ") else last
    return rc, json.loads(payload)


# --------------------------------------------------------------------------- #
# Tests.
# --------------------------------------------------------------------------- #


def test_missing_remote_url_returns_exit_2(
    remote_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AGENT_ORCHESTRA_REMOTE_URL", raising=False)
    monkeypatch.delenv("AGENT_ORCHESTRA_REMOTE_TOKEN", raising=False)
    rc, out = _invoke(
        remote_module,
        ["--template", "red-team-the-plan"],
        env={},
    )
    assert rc == remote_module.EXIT_CONFIG
    assert "AGENT_ORCHESTRA_REMOTE_URL" in out["error"]


def test_post_returns_run_id_then_polls_to_completion(
    remote_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: POST → polling → 200 report.md → exit 0."""
    handler = _Handler([
        ("/api/run", _FakeResp(200, b'{"run_id": "r-1"}')),
        # First poll: still running
        ("/api/runs/r-1", _FakeResp(200, b'{"status": "running", "events": [{"type": "stream"}]}')),
        # Second poll: completed
        ("/api/runs/r-1", _FakeResp(200, b'{"status": "completed", "events": [{"type": "stream"}, {"type": "run_completed"}], "final_content": "synth", "veto_report": {"approved": true, "confidence": 0.91}}')),
        ("/api/runs/r-1/report.md", _FakeResp(200, b"# Report\nbody", content_type="text/markdown")),
    ])

    # Speed up the test — no sleeps.
    monkeypatch.setattr(remote_module.time, "sleep", lambda _s: None)
    rc, out = _invoke(
        remote_module,
        ["--template", "red-team-the-plan", "--poll-interval", "0.01", "--timeout", "5"],
        env={"AGENT_ORCHESTRA_REMOTE_URL": "http://api.test"},
        side_effect=handler,
    )

    assert rc == 0
    assert out["mode"] == "remote"
    assert out["run_id"] == "r-1"
    assert out["status"] == "completed"
    assert "Report" in out["final_content_preview"]
    assert out["report_url"].endswith("/api/runs/r-1/report.md")
    # Auth header NOT set when token is unconfigured.
    post_call = next(c for c in handler.calls if c[0] == "POST")
    assert "Authorization" not in {k.title() for k in post_call[2]}


def test_bearer_token_is_sent_when_env_set(
    remote_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = _Handler([
        ("/api/run", _FakeResp(200, b'{"run_id": "auth-1"}')),
        ("/api/runs/auth-1", _FakeResp(200, b'{"status": "completed", "events": [], "final_content": "x", "veto_report": {"approved": true}}')),
        ("/api/runs/auth-1/report.md", _FakeResp(200, b"x", content_type="text/markdown")),
    ])
    monkeypatch.setattr(remote_module.time, "sleep", lambda _s: None)
    rc, _ = _invoke(
        remote_module,
        ["--template", "red-team-the-plan", "--poll-interval", "0.01"],
        env={
            "AGENT_ORCHESTRA_REMOTE_URL": "http://api.test",
            "AGENT_ORCHESTRA_REMOTE_TOKEN": "hunter2",
        },
        side_effect=handler,
    )
    assert rc == 0
    auth_headers = [
        c[2].get("Authorization") for c in handler.calls if c[2].get("Authorization")
    ]
    assert auth_headers and all(h == "Bearer hunter2" for h in auth_headers)


def test_post_401_returns_exit_2_with_clear_message(
    remote_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = _Handler([
        ("/api/run", _FakeResp(401, b'{"detail": "authentication required"}')),
    ])
    monkeypatch.setattr(remote_module.time, "sleep", lambda _s: None)

    def _raise_401(req, timeout=None):                               # noqa: ANN001
        # urllib raises HTTPError on 4xx — emulate it for /api/run.
        if "/api/run" in req.full_url and req.get_method() == "POST":
            raise urllib.error.HTTPError(
                req.full_url, 401, "Unauthorized",
                {"Content-Type": "application/json"},
                io.BytesIO(b'{"detail": "authentication required"}'),
            )
        return handler(req, timeout=timeout)                          # pragma: no cover

    rc, out = _invoke(
        remote_module,
        ["--template", "x"],
        env={"AGENT_ORCHESTRA_REMOTE_URL": "http://api.test"},
        side_effect=_raise_401,
    )
    assert rc == remote_module.EXIT_CONFIG
    assert "AGENT_ORCHESTRA_REMOTE_TOKEN" in out["error"]


def test_network_error_on_post_returns_exit_6(
    remote_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(_req, timeout=None):                                  # noqa: ANN001
        raise urllib.error.URLError("connection refused")

    rc, out = _invoke(
        remote_module,
        ["--template", "x"],
        env={"AGENT_ORCHESTRA_REMOTE_URL": "http://api.test"},
        side_effect=_raise,
    )
    assert rc == remote_module.EXIT_NETWORK
    assert "network" in out["error"].lower()


def test_lucas_veto_in_final_returns_exit_4(
    remote_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = _Handler([
        ("/api/run", _FakeResp(200, b'{"run_id": "v-1"}')),
        ("/api/runs/v-1", _FakeResp(200, b'{"status": "completed", "events": [], "final_content": "blocked", "veto_report": {"approved": false, "reasons": ["fearmongering"]}}')),
        ("/api/runs/v-1/report.md", _FakeResp(404, b"")),
    ])
    monkeypatch.setattr(remote_module.time, "sleep", lambda _s: None)
    rc, out = _invoke(
        remote_module,
        ["--template", "x", "--poll-interval", "0.01"],
        env={"AGENT_ORCHESTRA_REMOTE_URL": "http://api.test"},
        side_effect=handler,
    )
    assert rc == remote_module.EXIT_VETOED
    assert out["veto_report"]["approved"] is False


def test_truncate_for_preview_is_byte_safe(remote_module) -> None:
    """Multi-byte chars + image-link awareness — never split inside ![](...)."""
    raw = "head\n" + ("X" * 12000) + "\n![alt](path/to/image.png)\ntail"
    out = remote_module._truncate_for_preview(raw, max_bytes=1024)
    assert "(truncated;" in out
    # Must NOT end mid-bracket.
    assert "![alt](path/to/image.png)" in out or "tail" in out
