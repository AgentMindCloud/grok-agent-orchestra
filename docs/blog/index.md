# Blog

Long-form writeups — benchmarks, post-mortems, design walkthroughs.
The first benchmark cycle and any case study work lives here.

## Posts

- [_(pending)_ **Orchestra vs GPT-Researcher — head-to-head benchmark, round 1**](2026-04-orchestra-vs-gpt-researcher.md)
  — methodology, 12 goals across 4 domains, third-party LLM-as-judge.
  Numbers populate when [the harness](../../benchmarks/) lands its first
  public run.

## Cadence

Benchmark posts re-run on the recurring schedule defined in
`.github/workflows/benchmarks.yml` (manual trigger + monthly
schedule + on every release tag). Each new run opens a PR with the
updated `comparison.md`; the post here gets a fresh "Round N"
addendum once the PR merges.
