"""SKILL: choose_template.py — token-overlap heuristic, no network.

Loads the bundled ``skills/agent-orchestra/templates/INDEX.json``
directly so the heuristic is exercised against the same data Claude
would see at runtime.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "skills" / "agent-orchestra" / "scripts" / "choose_template.py"
_INDEX = _REPO / "skills" / "agent-orchestra" / "templates" / "INDEX.json"


@pytest.fixture(scope="module")
def choose_module():
    """Import choose_template.py as a module without putting it on PYTHONPATH."""
    spec = importlib.util.spec_from_file_location("choose_template", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(choose_module, query: str, **kw) -> dict:
    """Invoke choose_template.main() and parse the single stdout line."""
    import io
    from contextlib import redirect_stdout

    argv = ["--query", query]
    for k, v in kw.items():
        argv.extend([f"--{k.replace('_', '-')}", str(v)])
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = choose_module.main(argv)
    return rc, json.loads(buf.getvalue().strip().splitlines()[-1])


# --------------------------------------------------------------------------- #
# Routing — every case below is something Claude users actually type.
# --------------------------------------------------------------------------- #


def test_competitive_analysis_query_surfaces_competitive_analysis(choose_module) -> None:
    """Canonical 'competitive analysis' phrasing should land in the
    top-2. The looser 'competitor brief' phrasing is genuinely
    ambiguous (overlaps with product-launch-**brief**); the SKILL
    confirms with the user whenever confidence is low, so the routing
    test focuses on the unambiguous canonical phrasing."""
    rc, out = _run(choose_module, "competitive analysis of Anthropic in 2026")
    assert rc == 0
    assert out["ok"] is True
    candidates = [out["top"]["slug"]] + [a["slug"] for a in out["alternates"]]
    assert "competitive-analysis" in candidates[:2]


def test_red_team_query_routes_to_red_team_template(choose_module) -> None:
    rc, out = _run(choose_module, "red-team the plan we shipped last quarter")
    assert rc == 0
    assert out["top"]["slug"] == "red-team-the-plan"


def test_arxiv_summary_routes_to_paper_summarizer(choose_module) -> None:
    rc, out = _run(choose_module, "summarize this arxiv paper on transformers")
    assert rc == 0
    assert out["top"]["slug"] == "paper-summarizer"


def test_weekly_digest_routes_with_high_confidence(choose_module) -> None:
    """Three strong tokens line up — confidence should clear 0.6."""
    rc, out = _run(choose_module, "weekly news digest about LLMs")
    assert rc == 0
    assert out["top"]["slug"] == "weekly-news-digest"
    assert out["top"]["confidence"] >= 0.6


def test_ambiguous_query_returns_alternates(choose_module) -> None:
    """Vague queries still pick *something* but populate alternates so
    the SKILL prompt knows to confirm with the user."""
    rc, out = _run(choose_module, "tell me about AI")
    assert rc == 0
    assert out["top"]["slug"] is not None
    assert isinstance(out["alternates"], list)
    assert len(out["alternates"]) >= 1


def test_top_k_returns_n_alternates(choose_module) -> None:
    rc, out = _run(choose_module, "deep research on agent frameworks", top_k=5)
    assert rc == 0
    assert len(out["alternates"]) == 5


# --------------------------------------------------------------------------- #
# Failure paths.
# --------------------------------------------------------------------------- #


def test_empty_query_returns_exit_3(choose_module) -> None:
    rc, out = _run(choose_module, "")
    assert rc == 3
    assert out["ok"] is False


def test_missing_index_file_returns_exit_2(
    choose_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Override the index path to a non-existent file."""
    monkeypatch.setenv("AGENT_ORCHESTRA_SKILL_INDEX", str(tmp_path / "missing.json"))
    rc, out = _run(choose_module, "any query")
    assert rc == 2
    assert "not found" in out["error"].lower()


def test_min_confidence_threshold_can_force_alternates_only(choose_module) -> None:
    rc, out = _run(choose_module, "tell me about AI", min_confidence=0.99)
    assert rc == 3
    assert out["ok"] is False
    assert "alternates" in out


def test_index_carries_eighteen_templates(choose_module) -> None:
    """Sanity-check the bundled catalog matches the upstream count."""
    raw = json.loads(_INDEX.read_text(encoding="utf-8"))
    assert len(raw["templates"]) == 18
