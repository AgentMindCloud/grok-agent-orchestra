# Placeholder — pre-launch state

This file is the include target for
[`docs/architecture/comparison.md`](../../docs/architecture/comparison.md)
and the round-1 blog post. It ships in the repo so the docs site
builds cleanly before the first benchmark run lands.

When the recurring workflow at `.github/workflows/benchmarks.yml`
lands its first green run, `_update_latest()` in
`benchmarks/harness.py` rewrites this file as a symlink to that
run's `comparison.md` — the seven canonical section headings below
get replaced with real numbers. Until then, the docs site shows the
prose above the include block.

## Headline numbers

_No public benchmark run has landed yet._

The harness ships in `benchmarks/`. The recurring workflow runs
monthly + on every release tag and opens a PR with real numbers
once the four required secrets (`XAI_API_KEY`, `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `TAVILY_API_KEY`) are configured. **No
fabricated numbers will ever ship in this file.**

## Aggregate by system

_(populated by the renderer after the first run)_

## Per-goal results

_(populated by the renderer after the first run)_

## Where each system wins

_(populated by the renderer after the first run)_

## Notable vetoes

_(populated by the renderer after the first run)_

## Honest limitations

The methodology lives at
[`benchmarks/methodology.md`](../methodology.md) — read it before
the numbers land so the inevitable "but this is biased toward X"
critique has a rubric to argue against.

## Reproducibility

Anyone with the four required API keys can run the harness:

```bash
python -m benchmarks.harness
```

…and `latest.md` will rewrite to point at their fresh run. The
methodology guarantees byte-equal reproducibility within the
documented inter-rater + wall-time tolerances.
