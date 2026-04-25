#!/usr/bin/env python3
"""Pick the best Agent Orchestra template for a free-text task description.

Why this exists
---------------
The skill's SKILL.md tells Claude to call this when the user hasn't
named a template explicitly. The scorer is a deliberately small
token-overlap heuristic over the bundled INDEX.json (no LLM, no
network, no `pyyaml` — stdlib only) so the skill never has to wait
on a model call just to dispatch a model call.

The scoring is intentionally generous: name + description + categories
each contribute, with a small bias toward exact category hits because
those are the human-curated buckets. Good enough to route 80%+ of
common phrasings ("competitor brief", "red-team my plan", "summarise
this paper", "weekly news digest") to the right template; ambiguous
queries return a low confidence + populated `alternates` so the SKILL
prompt can ask Claude to confirm with the user.

stdout (single line, JSON):
    {
      "ok": true,
      "query": "...",
      "top": {slug, name, score, confidence, estimated_tokens, ...},
      "alternates": [{slug, name, score, ...}, ...]
    }

Exit codes:
    0 — picked a template (or low-confidence fallback with alternates)
    2 — INDEX.json missing or malformed
    3 — query was empty
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Words that don't help routing — strip from both query + corpus before
# scoring. Kept tiny on purpose; the goal is to remove pure-noise tokens,
# not full English stop-word filtering.
_NOISE = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "at",
        "with", "from", "by", "is", "are", "be", "this", "that", "these",
        "those", "i", "we", "us", "you", "your", "my", "me", "do", "make",
        "give", "want", "need", "please", "can", "could", "would",
    }
)


def _index_path() -> Path:
    """Locate INDEX.json — either inside the skill (the production path)
    or via an explicit override (used by tests)."""
    override = os.environ.get("AGENT_ORCHESTRA_SKILL_INDEX")
    if override:
        return Path(override)
    here = Path(__file__).resolve().parent
    return here.parent / "templates" / "INDEX.json"


def _load_index(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"INDEX.json not found at {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    templates = raw.get("templates")
    if not isinstance(templates, list):
        raise ValueError("INDEX.json missing 'templates' list")
    return templates


def _tokens(text: str) -> set[str]:
    """Lowercased word tokens with noise + 1-char tokens stripped."""
    if not text:
        return set()
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text.lower())
    return {t for t in raw if len(t) > 1 and t not in _NOISE}


def _score(template: dict[str, Any], query_tokens: set[str]) -> float:
    """Weighted token-overlap score in roughly [0, 1].

    Weights:
      categories  — 3.0  (human-curated buckets are the strongest signal)
      name        — 2.0
      description — 1.0  (plenty of words; lower per-hit weight)
      slug        — 1.5  (catches "red-team-the-plan" style requests)
    Normalised by query token count so longer queries don't artificially
    inflate scores.
    """
    if not query_tokens:
        return 0.0

    cat_tokens = set()
    for c in template.get("categories", []) or []:
        cat_tokens |= _tokens(str(c).replace("-", " "))

    name_tokens = _tokens(str(template.get("name", "")))
    desc_tokens = _tokens(str(template.get("description", "")))
    slug_tokens = _tokens(str(template.get("slug", "")).replace("-", " "))

    score = (
        3.0 * len(query_tokens & cat_tokens)
        + 2.0 * len(query_tokens & name_tokens)
        + 1.0 * len(query_tokens & desc_tokens)
        + 1.5 * len(query_tokens & slug_tokens)
    )
    # Normalise by best-case-per-token (3 + 2 + 1 + 1.5 = 7.5)
    return round(score / (len(query_tokens) * 7.5), 4)


def _confidence(top_score: float, runner_up_score: float) -> float:
    """Margin-based confidence: score itself + a gap bonus over #2.

    A clear winner with a gap = high confidence; a flat distribution
    = low confidence even if the absolute score is OK.
    """
    if top_score <= 0:
        return 0.0
    margin = max(0.0, top_score - runner_up_score)
    return round(min(1.0, top_score * 1.5 + margin * 2.0), 4)


def _summary(template: dict[str, Any], score: float) -> dict[str, Any]:
    return {
        "slug": template.get("slug"),
        "name": template.get("name"),
        "score": score,
        "estimated_tokens": template.get("estimated_tokens"),
        "categories": template.get("categories", []),
        "description": (str(template.get("description", "")).strip() or None),
        "mode": template.get("mode"),
        "pattern": template.get("pattern"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True, help="User's free-text task description.")
    parser.add_argument(
        "--top-k", type=int, default=3,
        help="Number of alternates to surface alongside the top pick (default 3).",
    )
    parser.add_argument(
        "--min-confidence", type=float, default=0.0,
        help="Refuse to recommend if top confidence is below this threshold (exit 3).",
    )
    args = parser.parse_args(argv)

    query = (args.query or "").strip()
    if not query:
        print(json.dumps({"ok": False, "error": "empty query"}), file=sys.stdout)
        return 3

    try:
        index = _load_index(_index_path())
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stdout)
        return 2

    qtokens = _tokens(query)
    scored = sorted(
        ((t, _score(t, qtokens)) for t in index),
        key=lambda pair: pair[1],
        reverse=True,
    )
    top_template, top_score = scored[0]
    runner_up_score = scored[1][1] if len(scored) > 1 else 0.0
    confidence = _confidence(top_score, runner_up_score)

    if confidence < args.min_confidence:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"top confidence {confidence} below threshold {args.min_confidence}",
                    "alternates": [_summary(t, s) for t, s in scored[: args.top_k]],
                }
            )
        )
        return 3

    out = {
        "ok": True,
        "query": query,
        "top": {**_summary(top_template, top_score), "confidence": confidence},
        "alternates": [_summary(t, s) for t, s in scored[1 : args.top_k + 1]],
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
