---
title: "Orchestra vs GPT-Researcher — head-to-head benchmark, round 1"
date: 2026-04-25
authors: [agentmindcloud]
tags: [benchmarks, gpt-researcher, multi-agent]
---

# Orchestra vs GPT-Researcher — head-to-head benchmark, round 1

We shipped Agent Orchestra v1.0 with a strong opinion: multi-agent
research with a visible debate and an enforceable safety veto beats
single-agent research with a hidden one. Opinion is cheap. The
project now has a benchmark harness, a 12-goal corpus across four
domains, and a third-party LLM-as-judge to grade the receipts.

This post is the **round-1 writeup**. It pairs with the canonical
report at [`docs/architecture/comparison.md`](../architecture/comparison.md),
which auto-includes whatever `benchmarks/results/latest.md` is on
the day you read this. If you want the methodology in detail, head
to [`benchmarks/methodology.md`](https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/benchmarks/methodology.md).

## What we measured

Twelve goals — three each in tech, finance, science, operations.
Each goal runs against four systems:

- `orchestra-grok` — Agent Orchestra with the native xAI multi-agent endpoint.
- `orchestra-litellm` — Agent Orchestra routed through LiteLLM/OpenAI for parity.
- `gpt-researcher-default` — stock GPT-Researcher with research-report mode.
- `gpt-researcher-deep` — GPT-Researcher's deep-research mode.

Per (system × goal) we capture: tokens (in/out), dollar cost, wall
time, citation count, unique-domain count, audit lines per dollar,
plus four LLM-as-judge fields (citation relevance, citation support
strength, factual score against curated reference bullets, and
unsupported-claim count). The judge is a non-Grok model — defaults
to `claude-sonnet-4-6` via LiteLLM. We do not let Lucas judge his
own work.

## The receipts

_Round 1 is a placeholder until the recurring workflow lands a green
run. The block below auto-includes
`benchmarks/results/latest.md`; before the first run it renders
empty. Re-read this page once the launch PR merges._

{%
  include-markdown "../../benchmarks/results/latest.md"
  start="## Headline numbers"
  rewrite-relative-urls=false
%}

## What this round changed

- We have a frozen 12-goal corpus. Future runs measure against the
  same prompts; the curated reference bullets get small refreshes
  per quarter as facts move.
- The judge has a documented inter-rater calibration (≥ 0.78 on
  citation relevance, 0.72 on support strength, on the 0-3 scales).
  Below 0.5 triggers a re-run.
- Every run is reproducible — drop a third-party auditor on
  `manifest.json` and they can re-render the report without
  re-spending the credits.

## Where Orchestra wins, where it doesn't

We don't suppress losing rows. The per-goal table in the
`comparison.md` shows everything; the `## Where each system wins`
section names the per-metric winner. The expected pattern, which
the harness will confirm or refute:

- **Orchestra wins on audit-lines-per-dollar by a wide margin.**
  Multi-role debate with full event capture is structurally more
  inspectable than a single-agent loop. (Caveat: that doesn't make
  it cheaper per goal — it usually doesn't.)
- **Orchestra wins on factual_score when the goal needs adversarial
  review.** Lucas catches one-sided framing the others miss.
- **GPT-Researcher wins on cost for one-shot summarisation.** Less
  loop, less spend. We surface those rows without softening.
- **GPT-Researcher wins on wall time for shallow goals.** No
  multi-round debate to amortize.

## Honest limitations

The judge has biases. Pricing snapshots age. Wall time is noisy.
Hallucination rate is heuristic. Methodology spells out exactly
where each of these can move the headline; the per-goal table makes
it easy to re-aggregate by your own weights.

## Re-running

```bash
pip install -e ".[benchmarks]"
export XAI_API_KEY=...     OPENAI_API_KEY=...
export TAVILY_API_KEY=...  ANTHROPIC_API_KEY=...
python -m benchmarks.harness
```

The CI workflow at `.github/workflows/benchmarks.yml` runs the
harness on the live PyPI release monthly (and on every tag) and
opens a PR with the updated `comparison.md`. We don't auto-publish
benchmark numbers — every PR gets a human review.
