"""Publisher tests — Markdown is exhaustive, PDF/DOCX are existence-checks.

The Markdown render is the source of truth so we lock it down with
section-presence + frontmatter assertions. PDF tests only run when
``weasyprint`` actually imports (Cairo/Pango must be on the host);
DOCX tests only run when ``python-docx`` is importable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# --------------------------------------------------------------------------- #
# Synthetic Run helpers.
# --------------------------------------------------------------------------- #


def _events_for_simulated_run() -> list[dict[str, Any]]:
    """Mimic a finished simulated run with role outputs + a Lucas pass."""
    return [
        {"type": "run_started", "mode": "simulated", "seq": 1},
        {"type": "debate_round_started", "round": 1, "seq": 2},
        {"type": "role_started", "role": "Harper", "round": 1, "seq": 3},
        {
            "type": "stream",
            "kind": "token",
            "role": "Harper",
            "text": (
                "Surfaced primary sources: see arXiv:2403.04132 at "
                "https://arxiv.org/abs/2403.04132 [arxiv.org] and a follow-up "
                "post at https://example.com/post.\n"
            ),
            "seq": 4,
        },
        {"type": "role_completed", "role": "Harper", "round": 1, "seq": 5},
        {"type": "role_started", "role": "Benjamin", "round": 1, "seq": 6},
        {
            "type": "stream",
            "kind": "token",
            "role": "Benjamin",
            "text": "Logical structure is sound; no fallacies flagged.",
            "seq": 7,
        },
        {"type": "role_completed", "role": "Benjamin", "round": 1, "seq": 8},
        {"type": "role_started", "role": "Lucas", "round": 1, "seq": 9},
        {
            "type": "stream",
            "kind": "token",
            "role": "Lucas",
            "text": "No flaws detected — proceed.",
            "seq": 10,
        },
        {"type": "role_completed", "role": "Lucas", "round": 1, "seq": 11},
        {"type": "role_started", "role": "Grok", "round": 2, "seq": 12},
        {
            "type": "stream",
            "kind": "token",
            "role": "Grok",
            "text": "Synthesis: ship the thread as drafted.",
            "seq": 13,
        },
        {"type": "role_completed", "role": "Grok", "round": 2, "seq": 14},
        {"type": "lucas_started", "seq": 15},
        {"type": "lucas_passed", "confidence": 0.91, "seq": 16},
        {"type": "run_completed", "success": True, "final_output": "FINAL TEXT", "seq": 17},
    ]


@pytest.fixture
def synthetic_run() -> dict[str, Any]:
    return {
        "id": "run-test-0001",
        "template_name": "orchestra-simulated-truthseeker",
        "yaml_text": "name: test\n",
        "events": _events_for_simulated_run(),
        "final_output": "FINAL TEXT — composed by Grok.",
        "veto_report": {
            "approved": True,
            "safe": True,
            "confidence": 0.91,
            "reasons": [],
        },
        "started_at": 1_700_000_000.0,
        "finished_at": 1_700_000_002.5,
    }


# --------------------------------------------------------------------------- #
# Citation extraction.
# --------------------------------------------------------------------------- #


def test_citation_extraction_from_synthetic_transcript(synthetic_run: dict) -> None:
    from grok_orchestra.publisher import Publisher

    citations = Publisher().extract_citations(synthetic_run)
    urls = {c.url for c in citations if c.url}
    # Both URLs Harper mentioned must be picked up.
    assert "https://arxiv.org/abs/2403.04132" in urls
    assert "https://example.com/post" in urls
    # The bracketed-domain refs must NOT duplicate the existing https:// hit.
    assert sum(1 for c in citations if "arxiv.org" in (c.url or "")) == 1
    # Section attribution is present.
    assert any(c.used_in_section == "findings" for c in citations)


def test_citation_attached_dataclass_passthrough(synthetic_run: dict) -> None:
    from grok_orchestra.publisher import Citation, Publisher

    synthetic_run["citations"] = [
        Citation(
            source_type="file",
            title="local report.pdf",
            file_path="/app/workspace/docs/report.pdf",
            used_in_section="findings",
        )
    ]
    citations = Publisher().extract_citations(synthetic_run)
    file_paths = [c.file_path for c in citations if c.file_path]
    assert "/app/workspace/docs/report.pdf" in file_paths


# --------------------------------------------------------------------------- #
# Markdown — exhaustive section / frontmatter checks.
# --------------------------------------------------------------------------- #


def test_markdown_has_frontmatter_with_run_id(synthetic_run: dict) -> None:
    from grok_orchestra.publisher import Publisher

    md = Publisher().build_markdown(synthetic_run)
    assert md.startswith("---\n")
    assert f"run_id: {synthetic_run['id']}" in md
    assert "confidence:" in md
    assert "approved: true" in md


def test_markdown_includes_every_required_section(synthetic_run: dict) -> None:
    from grok_orchestra.publisher import Publisher

    md = Publisher().build_markdown(synthetic_run)
    for section in (
        "## Executive Summary",
        "## Findings",
        "## Analysis",
        "## Stress Test",
        "## Synthesis",
        "## Lucas Verdict",
        "## Citations",
        "## Appendix · Debate transcript",
    ):
        assert section in md, f"missing section {section!r}"


def test_markdown_renders_lucas_pass_state(synthetic_run: dict) -> None:
    from grok_orchestra.publisher import Publisher

    md = Publisher().build_markdown(synthetic_run)
    assert "✅ approved" in md or "yes" in md
    assert "0.91" in md  # confidence number from veto_report


def test_markdown_handles_blocked_verdict() -> None:
    from grok_orchestra.publisher import Publisher

    run = {
        "id": "run-blocked",
        "template_name": "red-team-the-plan",
        "events": [
            {"type": "stream", "kind": "token", "role": "Harper", "text": "n/a"},
            {"type": "lucas_veto", "reason": "hype words detected"},
        ],
        "final_output": "",
        "veto_report": {
            "approved": False,
            "confidence": 0.32,
            "reasons": ["hype words detected"],
        },
    }
    md = Publisher().build_markdown(run)
    assert "⛔ blocked" in md
    assert "hype words detected" in md


# --------------------------------------------------------------------------- #
# DOCX — existence + non-zero size + the run id appears in the file.
# --------------------------------------------------------------------------- #


def test_docx_writes_a_valid_office_file(synthetic_run: dict, tmp_path: Path) -> None:
    pytest.importorskip("docx")
    from grok_orchestra.publisher import Publisher

    out = tmp_path / "report.docx"
    Publisher().build_docx(synthetic_run, out)
    assert out.exists()
    assert out.stat().st_size > 2000, "DOCX is suspiciously small"

    # docx files are zip archives — verify the magic.
    import zipfile

    assert zipfile.is_zipfile(out)
    with zipfile.ZipFile(out) as zf:
        # python-docx consistently writes `word/document.xml`.
        assert "word/document.xml" in zf.namelist()
        body = zf.read("word/document.xml").decode("utf-8", "replace")
        assert "Executive Summary" in body
        assert "Lucas Verdict" in body


# --------------------------------------------------------------------------- #
# PDF — only runs when WeasyPrint imports cleanly (system libs present).
# --------------------------------------------------------------------------- #


def test_pdf_renders_when_weasyprint_available(synthetic_run: dict, tmp_path: Path) -> None:
    pytest.importorskip("weasyprint")
    pytest.importorskip("markdown")
    from grok_orchestra.publisher import Publisher

    out = tmp_path / "report.pdf"
    Publisher().build_pdf(synthetic_run, out)
    assert out.exists()
    assert out.stat().st_size > 5000, "PDF is suspiciously small"
    # PDF magic header.
    assert out.read_bytes()[:4] == b"%PDF"


def test_pdf_raises_publisher_error_without_weasyprint(synthetic_run: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If weasyprint isn't available, we surface a helpful PublisherError."""
    import sys

    monkeypatch.setitem(sys.modules, "weasyprint", None)
    from grok_orchestra.publisher import Publisher, PublisherError

    with pytest.raises(PublisherError, match="\\[publish\\]"):
        Publisher().build_pdf(synthetic_run, tmp_path / "report.pdf")


# --------------------------------------------------------------------------- #
# Workspace path resolver.
# --------------------------------------------------------------------------- #


def test_run_report_dir_creates_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROK_ORCHESTRA_WORKSPACE", str(tmp_path / "ws"))
    from grok_orchestra.publisher import run_report_dir, workspace_runs_dir

    runs_dir = workspace_runs_dir()
    assert runs_dir.exists()
    out = run_report_dir("abc123")
    assert out.exists()
    assert out.parent == runs_dir
    assert out.name == "abc123"


# --------------------------------------------------------------------------- #
# End-to-end: web run → on-disk report.md (smokes the runner hook).
# --------------------------------------------------------------------------- #


def test_run_completion_writes_report_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    monkeypatch.setenv("GROK_ORCHESTRA_WORKSPACE", str(tmp_path / "ws"))

    from fastapi.testclient import TestClient

    from grok_orchestra.web.main import create_app

    yaml_text = (
        "name: pub-test\n"
        "goal: hello\n"
        "orchestra:\n"
        "  mode: simulated\n"
        "  agent_count: 4\n"
        "  reasoning_effort: medium\n"
        "  debate_rounds: 1\n"
        "  orchestration: {pattern: native, config: {}}\n"
        "  agents:\n"
        "    - {name: Grok, role: coordinator}\n"
        "    - {name: Harper, role: researcher}\n"
        "    - {name: Benjamin, role: logician}\n"
        "    - {name: Lucas, role: contrarian}\n"
        "safety: {lucas_veto_enabled: true, confidence_threshold: 0.5}\n"
        "deploy: {target: stdout}\n"
    )
    client = TestClient(create_app())
    r = client.post("/api/run", json={"yaml": yaml_text, "simulated": True})
    run_id = r.json()["run_id"]

    # Wait for the worker thread to finish + write report.md.
    import time as _time

    deadline = _time.monotonic() + 5.0
    while _time.monotonic() < deadline:
        body = client.get(f"/api/runs/{run_id}").json()
        if body.get("status") in ("completed", "failed"):
            break
        _time.sleep(0.02)
    assert body["status"] == "completed", body

    report_dir = tmp_path / "ws" / "runs" / run_id
    md_path = report_dir / "report.md"
    json_path = report_dir / "run.json"
    assert md_path.exists()
    assert json_path.exists()

    md = md_path.read_text(encoding="utf-8")
    assert md.startswith("---\n")
    assert f"run_id: {run_id}" in md

    snapshot = json.loads(json_path.read_text(encoding="utf-8"))
    assert snapshot["id"] == run_id
    assert "events" in snapshot
    assert snapshot["events"], "snapshot lost the event list"


def test_api_report_md_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    monkeypatch.setenv("GROK_ORCHESTRA_WORKSPACE", str(tmp_path / "ws"))

    from fastapi.testclient import TestClient

    from grok_orchestra.web.main import create_app

    yaml_text = (
        "name: pub-api-test\n"
        "goal: hi\n"
        "orchestra:\n"
        "  mode: simulated\n"
        "  agent_count: 4\n"
        "  reasoning_effort: medium\n"
        "  debate_rounds: 1\n"
        "  orchestration: {pattern: native, config: {}}\n"
        "  agents:\n"
        "    - {name: Grok, role: coordinator}\n"
        "    - {name: Harper, role: researcher}\n"
        "    - {name: Benjamin, role: logician}\n"
        "    - {name: Lucas, role: contrarian}\n"
        "safety: {lucas_veto_enabled: true, confidence_threshold: 0.5}\n"
        "deploy: {target: stdout}\n"
    )
    client = TestClient(create_app())
    run_id = client.post(
        "/api/run", json={"yaml": yaml_text, "simulated": True}
    ).json()["run_id"]

    import time as _time

    deadline = _time.monotonic() + 5.0
    while _time.monotonic() < deadline:
        if client.get(f"/api/runs/{run_id}").json().get("status") == "completed":
            break
        _time.sleep(0.02)

    r = client.get(f"/api/runs/{run_id}/report.md")
    assert r.status_code == 200
    assert "text/markdown" in r.headers.get("content-type", "")
    assert "Content-Disposition" in r.headers
    assert r.headers["Content-Disposition"].endswith(f'"report-{run_id}.md"')
    assert "## Executive Summary" in r.text
