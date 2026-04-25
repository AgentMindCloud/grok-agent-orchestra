"""SKILL: run_orchestration.py — local CLI path, fully mocked subprocess.

The script spawns ``grok-orchestra run <spec> --json`` via
``subprocess.Popen`` and parses the trailing JSON line. Tests substitute
a fake ``Popen`` that exposes the same shape (stdout, stderr, wait,
returncode) so we never invoke a real subprocess in CI.
"""

from __future__ import annotations

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "skills" / "agent-orchestra" / "scripts" / "run_orchestration.py"


@pytest.fixture(scope="module")
def run_module():
    spec = importlib.util.spec_from_file_location("run_orchestration", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# Fake Popen — implements just enough surface for run_orchestration.py.
# --------------------------------------------------------------------------- #


class _FakeStream:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def __iter__(self):                                              # noqa: D401
        return iter(self._lines)

    def close(self) -> None:                                          # pragma: no cover
        return None


class _FakePopen:
    """Minimal Popen surface. Configure stdout, stderr, returncode."""

    def __init__(
        self,
        stdout_text: str = "",
        stderr_lines: list[str] | None = None,
        returncode: int = 0,
    ) -> None:
        self._stdout = stdout_text
        self.stderr = _FakeStream(stderr_lines or [])
        self.returncode = returncode

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        return self._stdout, ""

    def kill(self) -> None:                                           # pragma: no cover
        return None

    def wait(self, timeout: float | None = None) -> int:              # pragma: no cover
        return self.returncode


def _invoke(run_module, argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_module.main(argv)
    last = buf.getvalue().strip().splitlines()[-1]
    assert last.startswith("RESULT_JSON: ") or last.startswith("{"), last
    payload = last[len("RESULT_JSON: "):] if last.startswith("RESULT_JSON: ") else last
    return rc, json.loads(payload)


# --------------------------------------------------------------------------- #
# Tests.
# --------------------------------------------------------------------------- #


def test_no_mode_available_returns_exit_7(
    run_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AGENT_ORCHESTRA_REMOTE_URL", raising=False)
    monkeypatch.setattr(run_module.shutil, "which", lambda _name: None)
    rc, out = _invoke(run_module, ["--template", "red-team-the-plan"])
    assert rc == run_module.EXIT_NO_MODE
    assert out["ok"] is False
    assert "Neither" in out["error"]


def test_local_happy_path(
    run_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(run_module.shutil, "which", lambda _name: "/fake/grok-orchestra")
    monkeypatch.setenv("GROK_ORCHESTRA_WORKSPACE", str(tmp_path))

    captured: dict[str, Any] = {}
    cli_json = json.dumps(
        {
            "ok": True,
            "success": True,
            "duration_seconds": 1.2,
            "final_content": "synthesis text [web:example.com]",
            "veto_report": {"approved": True, "confidence": 0.91, "reasons": []},
            "run_id": "abc123",
        }
    )

    def _fake_popen(cmd, **kwargs):                                  # noqa: ANN001
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        return _FakePopen(stdout_text=f"hello\n{cli_json}\n", returncode=0)

    monkeypatch.setattr(run_module.subprocess, "Popen", _fake_popen)
    rc, out = _invoke(run_module, ["--template", "red-team-the-plan"])

    assert rc == 0
    assert out["mode"] == "local"
    assert out["success"] is True
    assert "synthesis text" in out["final_content_preview"]
    # Verifies the CLI's positional arg and --json flag are sent.
    assert captured["cmd"][:3] == ["/fake/grok-orchestra", "run", "red-team-the-plan"]
    assert "--json" in captured["cmd"]
    # Workspace env is propagated to the subprocess.
    assert captured["env"]["GROK_ORCHESTRA_WORKSPACE"] == str(tmp_path)


def test_local_dry_run_uses_dry_run_subcommand(
    run_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(run_module.shutil, "which", lambda _n: "/fake/grok-orchestra")
    monkeypatch.setenv("GROK_ORCHESTRA_WORKSPACE", str(tmp_path))

    captured: dict[str, Any] = {}

    def _fake_popen(cmd, **kwargs):                                  # noqa: ANN001
        captured["cmd"] = cmd
        return _FakePopen(stdout_text='{"ok": true, "final_content": "", "run_id": "x"}\n', returncode=0)

    monkeypatch.setattr(run_module.subprocess, "Popen", _fake_popen)
    rc, _ = _invoke(run_module, ["--template", "red-team-the-plan", "--dry-run"])
    assert rc == 0
    assert captured["cmd"][1] == "dry-run"


def test_local_veto_returns_exit_4(
    run_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(run_module.shutil, "which", lambda _n: "/fake/grok-orchestra")
    monkeypatch.setenv("GROK_ORCHESTRA_WORKSPACE", str(tmp_path))

    cli_json = json.dumps(
        {
            "ok": False,
            "success": False,
            "duration_seconds": 0.5,
            "final_content": "rejected synthesis",
            "veto_report": {"approved": False, "reasons": ["fearmongering"]},
            "run_id": "v1",
        }
    )

    def _fake_popen(cmd, **kwargs):                                  # noqa: ANN001
        return _FakePopen(
            stdout_text=cli_json + "\n",
            returncode=4,
        )

    monkeypatch.setattr(run_module.subprocess, "Popen", _fake_popen)
    rc, out = _invoke(run_module, ["--template", "red-team-the-plan"])

    assert rc == 4
    assert out["exit_code"] == 4
    assert out["veto_report"]["approved"] is False


def test_force_local_without_cli_returns_exit_7(
    run_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_module.shutil, "which", lambda _n: None)
    rc, out = _invoke(run_module, ["--template", "red-team-the-plan", "--force-local"])
    assert rc == run_module.EXIT_NO_MODE
    assert "force-local" in out["error"]


def test_force_remote_without_url_returns_exit_2(
    run_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AGENT_ORCHESTRA_REMOTE_URL", raising=False)
    rc, out = _invoke(run_module, ["--template", "x", "--force-remote"])
    assert rc == run_module.EXIT_CONFIG
    assert "AGENT_ORCHESTRA_REMOTE_URL" in out["error"]


def test_show_template_dumps_yaml_or_json(
    run_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--show <slug>` should print the template entry without spawning the CLI."""
    monkeypatch.setattr(run_module.shutil, "which", lambda _n: None)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_module.main(["--show", "red-team-the-plan"])
    assert rc == 0
    body = buf.getvalue()
    assert "red-team-the-plan" in body


def test_show_unknown_template_returns_exit_2(
    run_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_module.shutil, "which", lambda _n: None)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_module.main(["--show", "no-such-template"])
    assert rc == run_module.EXIT_CONFIG


def test_truncation_helper_handles_oversize_text(run_module) -> None:
    """remote_run._truncate_for_preview is shared between modes."""
    big = ("X" * 12000)
    out = run_module._truncate_for_preview(big, max_bytes=1024)
    assert len(out.encode("utf-8")) <= 2048    # head + tail + marker
    assert "(truncated;" in out
