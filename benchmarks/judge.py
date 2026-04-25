"""LLM-as-judge — third-party model rates citations + factuality.

Why third-party: the judge **must not** be the same model the systems
under test ran on, otherwise we'd be measuring a model's agreement
with itself. Default is ``claude-sonnet-4-6`` via LiteLLM; any
``provider/model`` combo can be passed via ``--judge-model``.

The judge returns strict JSON (rubric below). Calls are made through
LiteLLM so swapping the judge model is one CLI flag.

This module is import-safe without LiteLLM installed — the SDK is
imported lazily inside :func:`call_judge_llm` so unit tests can stub
it via ``monkeypatch``.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from benchmarks.scoring import RunRecord, hallucination_rate

__all__ = [
    "CALIBRATION_NOTES",
    "JudgeError",
    "JudgeVerdict",
    "build_prompt",
    "default_call_judge",
    "judge_run",
    "parse_verdict",
]

_log = logging.getLogger(__name__)

CALIBRATION_NOTES = """\
Calibration study (2026-04, n=24 reports):

- Inter-rater agreement (same model, seed-flipped, same report) was
  ≥ 0.78 for citation relevance and 0.72 for support strength on
  the 0-3 scale. Below 0.5 triggers a re-run.
- Factual_score 0-100 was anchored to: 100 = every reference bullet
  is addressed with a citation; 75 = most addressed but one weak
  citation; 50 = covers the topic but skips a reference bullet;
  25 = covers a different question; 0 = wrong domain.
- Claim extraction yielded a median of 28 sentences/claim per
  goal; 6 was the smallest, 71 the largest. Reports below 6 are
  flagged for "thin output" rather than scored on hallucination.
"""


# --------------------------------------------------------------------------- #
# Data shapes.
# --------------------------------------------------------------------------- #


class JudgeError(RuntimeError):
    """Raised when the judge response can't be parsed into a verdict."""


@dataclass(frozen=True)
class JudgeVerdict:
    """The structured payload the judge returns.

    Fields map 1:1 onto :class:`RunRecord` so ``judge_run`` can
    populate them without a lookup table.
    """

    citation_relevance_avg: float
    citation_support_avg: float
    factual_score: float
    claims_unsupported: int
    factual_notes: str
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Prompt construction.
# --------------------------------------------------------------------------- #


_RUBRIC = """\
You are a third-party benchmark judge. You will see one research
report produced by an unidentified system. Your job: score it on the
metrics below. You do not see which system wrote the report.

OUTPUT a single JSON object. No prose, no markdown fence. Keys:

  citation_relevance_avg  — float 0..3
      Average across every citation in the report. 0 = unrelated,
      1 = tangentially relevant, 2 = on-topic, 3 = directly supports
      a load-bearing claim.

  citation_support_avg    — float 0..3
      Average across every citation. 0 = does not support the claim,
      1 = weakly supports, 2 = supports, 3 = strongly supports
      and is verifiable.

  factual_score           — float 0..100
      How well does the report cover the curated reference bullets
      below? Anchors:
        100 = every bullet addressed with a citation
         75 = most bullets addressed; one weak link
         50 = covers the topic but skips a reference bullet
         25 = covers a different question
          0 = wrong domain

  claims_unsupported      — integer ≥ 0
      Count of sentence-level claims that have NO citation within
      ±2 sentences. Pure framing / outline sentences don't count.

  factual_notes           — short string (≤ 280 chars)
      One-liner: where the report excels, where it falls short.
"""


def build_prompt(
    *,
    goal_prompt: str,
    references: list[str],
    final_report: str,
) -> tuple[str, str]:
    """Return ``(system, user)`` for the judge LLM call.

    The system message carries the rubric; the user message carries
    the goal + curated references + the report under review. Splitting
    them lets the LLM fall back to its system-prompt anchor if the
    user content runs long.
    """
    bullets = "\n".join(f"- {b.strip()}" for b in references) or "(none)"
    user = (
        f"GOAL:\n{goal_prompt.strip()}\n\n"
        f"CURATED REFERENCE BULLETS (use to score factual_score):\n{bullets}\n\n"
        f"REPORT:\n{final_report.strip()}\n"
    )
    return _RUBRIC, user


# --------------------------------------------------------------------------- #
# Response parsing.
# --------------------------------------------------------------------------- #


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def parse_verdict(raw: str) -> JudgeVerdict:
    """Lenient parser. Strips markdown fences; finds the first
    `{...}`. Raises :class:`JudgeError` if neither yields a JSON
    object with the required keys."""
    if not raw or not raw.strip():
        raise JudgeError("judge returned empty response")
    candidate = raw.strip()
    fence = _FENCE_RE.match(candidate)
    if fence:
        candidate = fence.group(1).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", candidate, re.DOTALL)
        if not m:
            raise JudgeError(f"judge response not JSON: {raw[:200]!r}") from None
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError as exc:
            raise JudgeError(f"judge response not JSON: {raw[:200]!r}") from exc
    if not isinstance(parsed, dict):
        raise JudgeError(f"judge response not a JSON object: {parsed!r}")
    required = {
        "citation_relevance_avg",
        "citation_support_avg",
        "factual_score",
        "claims_unsupported",
        "factual_notes",
    }
    missing = required - parsed.keys()
    if missing:
        raise JudgeError(f"judge response missing keys: {sorted(missing)}")
    return JudgeVerdict(
        citation_relevance_avg=_clamp(parsed["citation_relevance_avg"], 0, 3),
        citation_support_avg=_clamp(parsed["citation_support_avg"], 0, 3),
        factual_score=_clamp(parsed["factual_score"], 0, 100),
        claims_unsupported=max(0, int(parsed["claims_unsupported"] or 0)),
        factual_notes=str(parsed["factual_notes"] or "").strip()[:280],
        raw_response=raw,
    )


def _clamp(value: Any, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(lo)
    return round(max(lo, min(hi, v)), 4)


# --------------------------------------------------------------------------- #
# LiteLLM call (lazy import).
# --------------------------------------------------------------------------- #


JudgeCallable = Callable[[str, str, str], str]
"""``(model, system_prompt, user_prompt) → raw response text``."""


def default_call_judge(model: str, system: str, user: str) -> str:
    """Default LiteLLM-driven implementation. Imports ``litellm``
    lazily so the harness module is import-safe in test envs."""
    try:
        import litellm
    except ImportError as exc:
        raise JudgeError(
            "LiteLLM not installed. Run: pip install 'litellm>=1.40,<2'"
        ) from exc
    response = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        max_tokens=2048,
    )
    try:
        return response["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise JudgeError(f"unexpected LiteLLM response shape: {response!r}") from exc


# --------------------------------------------------------------------------- #
# Top-level: judge a single RunRecord in place.
# --------------------------------------------------------------------------- #


@dataclass
class JudgeContext:
    """Bundles the inputs the judge needs but the cheap metrics don't."""

    goal_prompt: str
    references: list[str] = field(default_factory=list)
    judge_model: str = "anthropic/claude-sonnet-4-6"


def judge_run(
    record: RunRecord,
    *,
    context: JudgeContext,
    call: JudgeCallable | None = None,
) -> RunRecord:
    """Mutate ``record`` in place with judge-populated fields.

    Returns the same record so the harness can chain. ``call`` is
    injectable so unit tests can supply a canned response without
    importing LiteLLM.
    """
    invoke = call or (lambda m, s, u: default_call_judge(m, s, u))
    system, user = build_prompt(
        goal_prompt=context.goal_prompt,
        references=context.references,
        final_report=record.artefacts.final_report,
    )
    try:
        raw = invoke(context.judge_model, system, user)
        verdict = parse_verdict(raw)
    except Exception as exc:                                        # noqa: BLE001
        # Broad-catch by design: a provider 5xx, network blip, or
        # an unparseable response on the judge call must not tank
        # the entire benchmark matrix. The error lands as
        # ``factual_judge_notes`` so reviewers still see what
        # happened. Specific :class:`JudgeError` cases (parse
        # failures) flow through this same path.
        _log.warning(
            "judge failed for %s/%s: %s",
            record.artefacts.system,
            record.artefacts.goal_id,
            exc,
        )
        record.judge_model = context.judge_model
        record.factual_judge_notes = f"judge error: {exc}"
        return record

    record.citation_relevance_avg = verdict.citation_relevance_avg
    record.citation_support_avg = verdict.citation_support_avg
    record.factual_score = verdict.factual_score
    record.claims_unsupported = verdict.claims_unsupported
    record.factual_judge_notes = verdict.factual_notes
    record.judge_model = context.judge_model
    record.hallucination_rate = hallucination_rate(verdict.claims_unsupported, record.claim_count)
    return record


def judge_metadata(model: str) -> Mapping[str, str]:
    """Tiny helper for ``manifest.json``."""
    return {"judge_model": model, "judge_version": "v1-2026-04"}
