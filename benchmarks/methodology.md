# Benchmark methodology

This document is the contract between the harness and any reader who
wants to verify the numbers. Locked-in: read this **before** the
results table to know exactly what was measured and how.

## Systems under test

| ID | What it is | How it's invoked |
| --- | --- | --- |
| `orchestra-grok` | Agent Orchestra with native xAI multi-agent endpoint. | `grok-orchestra run <spec> --json` against `orchestra-native-4` (or whatever `slug` the goal points at). |
| `orchestra-litellm` | Agent Orchestra routed through the LiteLLM adapter, default OpenAI model. | Same CLI; `orchestra.llm.default.{provider: openai, model: gpt-4.1-mini}` injected at runtime. |
| `gpt-researcher-default` | [GPT-Researcher](https://github.com/assafelovic/gpt-researcher) with stock config. | `from gpt_researcher import GPTResearcher; await researcher.conduct_research(); await researcher.write_report()`. |
| `gpt-researcher-deep` | GPT-Researcher's deep-research mode. | Same lib with `report_type="deep"`. |

Every system runs every goal **exactly twice** — once on the same
fresh prompt — and the second run's numbers are reported. The first
is a warm-up to even out cache effects.

## Goals

Twelve goals across four domains: tech, finance, science, operations.
See `benchmarks/goals.yaml` for the verbatim prompts + curated
references the LLM-as-judge uses for factual scoring. The set is
deliberately broad enough that a single-shot LLM can plausibly answer
but multi-agent orchestration should win on citation density and
audit-trail depth.

## Metrics

Each (system × goal) result captures:

### Cost + latency

| Field | Source |
| --- | --- |
| `tokens_in` | provider usage report or token-count of input prompt |
| `tokens_out` | provider usage report or `tiktoken` count of final + transcripts |
| `cost_usd` | provider usage cost; falls back to `tokens × price-list` when absent |
| `wall_seconds` | `time.monotonic()` from spawn to final-report write |

Both Orchestra and GPT-Researcher report token counts in their
metadata; when missing we fall back to `tiktoken` counting.

### Citations

| Field | Source |
| --- | --- |
| `citations_count` | regex over the final report — `[scheme:target]` or HTTP URLs |
| `unique_domains` | set-of-host of `citations_count` (web only) |
| `citation_relevance_avg` | LLM-as-judge — 0-3 scale per citation, averaged |
| `citation_support_avg` | LLM-as-judge — 0-3 scale per citation, averaged |

### Audit trail

| Field | Source |
| --- | --- |
| `audit_lines` | wc -l of the run's complete event/transcript log |
| `audit_lines_per_dollar` | `audit_lines / cost_usd` (∞ when cost is 0) |

This is the metric that surfaces Orchestra's structural advantage:
every role turn, every tool call, every reasoning tick is on the
record. GPT-Researcher's stock log is shorter by design.

### Vetoes (Orchestra-only)

| Field | Source |
| --- | --- |
| `veto_triggered` | bool — did Lucas veto the synthesis? |
| `veto_reasons` | list of strings — Lucas's `reasons[]` payload |

We **do not** count vetoes as a quality win. The interesting axis
is *correctness of the veto* — when Lucas blocks output, does the
LLM-as-judge agree the output was problematic? That's a manual
review per veto, captured in the report's "Notable vetoes" section.

### Factual accuracy

| Field | Source |
| --- | --- |
| `factual_score` | LLM-as-judge — 0-100 against the goal's curated `reference[]` |
| `factual_judge_notes` | the judge's free-text explanation per goal |

### Hallucination rate

| Field | Source |
| --- | --- |
| `claim_count` | LLM-as-judge claim-extraction over the final report |
| `claims_unsupported` | claims with no nearby citation (within ±2 sentences) |
| `hallucination_rate` | `claims_unsupported / claim_count` |

A claim is "supported" when the LLM-as-judge can match a citation in
its ±2-sentence window AND the citation source plausibly backs the
claim. The judge prompt + rubric live in `benchmarks/judge.py`.

## LLM-as-judge

**Independent third-party model.** We deliberately do **not** use
Lucas (`grok-4.20-0309`) or any model the systems-under-test relied
on. The default judge is `claude-sonnet-4-6` via LiteLLM; any
provider/model combo can be swapped via `--judge-model
<provider>/<model>` on the harness CLI.

The judge sees only:

1. The goal prompt + the goal's curated `reference[]`.
2. The system's final report.
3. The judging rubric (locked in `benchmarks/judge.py`).

It never sees which system produced the report. Reports are passed
in randomised order per goal so the judge can't anchor on patterns.

Judge consistency is checked by re-judging a 20% sample with the
seed flipped and comparing scores. Inter-rater drift > 0.5 on the
0-3 scales triggers a re-run.

## Pricing

Token → cost conversion uses the [`benchmarks/pricing.json`](pricing.json)
table, which is regenerated from each provider's public price list at
the start of every benchmark run. The pricing snapshot is included
in the result file so historical comparisons stay valid even after
prices move.

## Reproducibility

Every harness run writes to
`benchmarks/results/<YYYY-MM>-<seed>/` containing:

| File | Contents |
| --- | --- |
| `manifest.json` | systems-under-test versions, judge model, pricing snapshot, seed, git SHA |
| `<system>__<goal-id>.json` | per-run metric record (the canonical artefact) |
| `<system>__<goal-id>.transcript.txt` | full audit trail (one event per line) |
| `<system>__<goal-id>.report.md` | the system's final report verbatim |
| `comparison.md` | rendered report (the same file `mkdocs` includes) |
| `charts/*.svg` | generated by `benchmarks/charts.py` |

Anyone with API keys can re-run: `python -m benchmarks.harness --seed
<the-seed>`. The harness prints a checksum manifest so a third-party
auditor can confirm they ran the same prompts.

## Honest limitations

- **The judge has biases.** A larger/cheaper/different judge model
  may rate citations differently. We mitigate by publishing the
  judge prompts verbatim and re-running with seed-flips.
- **Tavily / Brave / Bing / Serper differ.** GPT-Researcher and
  Orchestra both default to Tavily, but a different search backend
  changes citation quality. We pin Tavily for both default
  configurations so the search layer is the same.
- **Cost numbers move.** They were correct on the run date in
  `manifest.json`. Re-running 6 months later may produce different
  cost numbers without any code change.
- **Wall-time is noisy.** Network latency to OpenAI / xAI varies by
  region + time-of-day. We report each goal's median across the
  warm-up + measured runs.
- **Hallucination rate is hard.** "Unsupported claim" is a
  judgement call. The 0-3 rubric and the ±2-sentence window were
  picked after a small calibration study (documented in
  `benchmarks/judge.py:CALIBRATION_NOTES`). Reasonable people can
  argue with both; the harness exposes the judge transcript so
  reviewers can audit.
- **GPT-Researcher cooperates differently with vetoes.** When the
  judge thinks a Lucas veto was correct, that's a quality win for
  Orchestra — but if Orchestra never runs the synthesis at all,
  the cost-per-result tilts the wrong way. We surface both numbers
  and let the reader decide.

## What "winning" means here

Different goals reward different things. The aggregate winner in
the comparison table is the system with the most per-metric wins,
not the lowest cost or the most citations. We publish the full
per-goal table so anyone can re-aggregate by their own weights.
