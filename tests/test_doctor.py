"""Tests for ``grok-orchestra doctor``.

The probe never leaves the box: ``urllib.request.urlopen`` is mocked,
``os.environ`` is monkeypatched. BYOK contract — env-var *presence*
is reported but the *value* is never read or echoed.
"""

from __future__ import annotations

import json
import urllib.error
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from grok_orchestra import cli as cli_module

runner = CliRunner()


# --------------------------------------------------------------------------- #
# Fake Ollama responses for the urllib probe.
# --------------------------------------------------------------------------- #


def _ollama_response(models: list[dict[str, Any]] | None = None) -> Any:
    """Mimic ``urllib.request.urlopen`` returning the Ollama tags shape."""

    class _Resp:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._payload = payload

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

    return _Resp({"models": models or []})


def _ollama_unreachable(*_args: Any, **_kwargs: Any) -> Any:
    """Mimic an OS-level connection refusal."""
    raise urllib.error.URLError("connection refused")


# --------------------------------------------------------------------------- #
# Cloud key probe — env presence only.
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _scrub_cloud_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with NO cloud keys in the environment."""
    for name in (
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "MISTRAL_API_KEY",
        "GROQ_API_KEY",
        "TOGETHER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------- #
# JSON output — the canonical contract for the dashboard / CI to consume.
# --------------------------------------------------------------------------- #


def test_doctor_json_demo_only_when_nothing_configured() -> None:
    with patch(
        "grok_orchestra.cli.urllib.request.urlopen",
        new=_ollama_unreachable,
    ):
        result = runner.invoke(cli_module.app, ["--json", "doctor"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["modes"]["demo"]["ready"] is True
    assert payload["modes"]["local"]["ready"] is False
    assert payload["modes"]["cloud"]["ready"] is False
    assert payload["modes"]["cloud"]["keys_present"] == []


def test_doctor_json_local_ready_when_ollama_responds() -> None:
    with patch(
        "grok_orchestra.cli.urllib.request.urlopen",
        return_value=_ollama_response(
            [{"name": "llama3.1:8b"}, {"name": "qwen2.5:3b"}]
        ),
    ):
        result = runner.invoke(cli_module.app, ["--json", "doctor"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["modes"]["local"]["ready"] is True
    assert "llama3.1:8b" in payload["modes"]["local"]["models"]
    assert "qwen2.5:3b" in payload["modes"]["local"]["models"]


def test_doctor_json_cloud_ready_when_xai_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "<paste-yours-here>")
    with patch(
        "grok_orchestra.cli.urllib.request.urlopen",
        new=_ollama_unreachable,
    ):
        result = runner.invoke(cli_module.app, ["--json", "doctor"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    cloud = payload["modes"]["cloud"]
    assert cloud["ready"] is True
    assert "XAI_API_KEY" in cloud["keys_present"]
    # BYOK: only NAMES are surfaced, never values.
    raw_blob = json.dumps(payload)
    assert "<paste-yours-here>" not in raw_blob


def test_doctor_json_reports_all_three_when_everything_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "<paste-yours-here>")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "<paste-yours-here>")
    with patch(
        "grok_orchestra.cli.urllib.request.urlopen",
        return_value=_ollama_response([{"name": "llama3.1:8b"}]),
    ):
        result = runner.invoke(cli_module.app, ["--json", "doctor"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["modes"]["demo"]["ready"] is True
    assert payload["modes"]["local"]["ready"] is True
    assert payload["modes"]["cloud"]["ready"] is True
    assert {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}.issubset(
        set(payload["modes"]["cloud"]["keys_present"])
    )


# --------------------------------------------------------------------------- #
# Rich-panel output — visible status messages the user actually reads.
# --------------------------------------------------------------------------- #


def test_doctor_rich_output_shows_demo_ready_always() -> None:
    with patch(
        "grok_orchestra.cli.urllib.request.urlopen",
        new=_ollama_unreachable,
    ):
        result = runner.invoke(cli_module.app, ["doctor"])
    assert result.exit_code == 0
    assert "Demo mode ready" in result.stdout


def test_doctor_rich_output_warns_when_local_unavailable() -> None:
    with patch(
        "grok_orchestra.cli.urllib.request.urlopen",
        new=_ollama_unreachable,
    ):
        result = runner.invoke(cli_module.app, ["doctor"])
    assert result.exit_code == 0
    # The exact unicode mark might be stripped by the test renderer; assert
    # by the substantive phrase the user sees.
    assert "Local mode unavailable" in result.stdout
    assert "ollama pull" in result.stdout


def test_doctor_rich_output_warns_when_no_cloud_keys() -> None:
    with patch(
        "grok_orchestra.cli.urllib.request.urlopen",
        new=_ollama_unreachable,
    ):
        result = runner.invoke(cli_module.app, ["doctor"])
    assert result.exit_code == 0
    assert "No cloud keys detected" in result.stdout
    assert "XAI_API_KEY" in result.stdout


def test_doctor_does_not_print_raw_key_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BYOK: the doctor command must never echo a raw key value."""
    secret = "<paste-yours-here>"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    with patch(
        "grok_orchestra.cli.urllib.request.urlopen",
        new=_ollama_unreachable,
    ):
        result = runner.invoke(cli_module.app, ["doctor"])
    assert result.exit_code == 0
    assert secret not in result.stdout
    # The variable NAME is fine to print; only the value is sensitive.
    assert "OPENAI_API_KEY" in result.stdout


# --------------------------------------------------------------------------- #
# Ollama URL + timeout overrides.
# --------------------------------------------------------------------------- #


def test_doctor_respects_custom_ollama_url() -> None:
    captured: list[str] = []

    def _capture(req: Any, timeout: float = 0) -> Any:
        del timeout
        captured.append(req.full_url if hasattr(req, "full_url") else req)
        return _ollama_response().__enter__()

    with patch("grok_orchestra.cli.urllib.request.urlopen", new=_capture):
        result = runner.invoke(
            cli_module.app,
            ["--json", "doctor", "--ollama-url", "http://10.0.0.5:9999"],
        )
    assert result.exit_code == 0
    assert any("10.0.0.5:9999" in u for u in captured)


def test_doctor_smoke_uses_short_timeout() -> None:
    """Sanity: the default timeout is bounded so the command stays snappy."""
    captured: list[float] = []

    def _capture(_req: Any, timeout: float = 0) -> Any:
        captured.append(timeout)
        raise urllib.error.URLError("nope")

    with patch("grok_orchestra.cli.urllib.request.urlopen", new=_capture):
        runner.invoke(cli_module.app, ["doctor"])
    assert captured and captured[0] <= 2.0


# --------------------------------------------------------------------------- #
# Local-only template parses + validates + every role pinned to Ollama.
# --------------------------------------------------------------------------- #


def test_local_only_template_parses_and_validates() -> None:
    from pathlib import Path

    from grok_orchestra.parser import load_orchestra_yaml

    path = Path(__file__).resolve().parent.parent / "examples" / "local-only" / "local-research.yaml"
    assert path.exists(), f"missing example template: {path}"
    config = load_orchestra_yaml(path)
    assert config is not None


def test_local_only_template_pins_every_role_to_ollama() -> None:
    from pathlib import Path

    from grok_orchestra.llm import resolve_role_models
    from grok_orchestra.parser import load_orchestra_yaml

    path = Path(__file__).resolve().parent.parent / "examples" / "local-only" / "local-research.yaml"
    config = load_orchestra_yaml(path)
    role_names = [a["name"] for a in config["orchestra"]["agents"]]
    role_models = resolve_role_models(config, role_names)
    assert role_models, "expected resolved role models"
    for name, model in role_models.items():
        assert model.startswith("ollama/"), f"{name} → {model} not pinned to ollama"
