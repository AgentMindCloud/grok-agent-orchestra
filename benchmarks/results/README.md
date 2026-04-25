# `benchmarks/results/`

Each subdirectory is one harness run. `latest.md` is a copy / symlink
to the most recent run's `comparison.md` so the docs site can
include-markdown a stable path.

## Per-run contents

Every `<YYYY-MM>-<seed>/` directory contains:

| File | What it is |
| --- | --- |
| `manifest.json` | seed, git SHA, judge model, plan, aggregates |
| `comparison.md` | rendered report (the file the docs site includes) |
| `<system>__<goal-id>.json` | one canonical record per (system × goal) |
| `charts/*.svg` | matplotlib charts (optional; missing when matplotlib isn't installed) |

The per-run JSON is the source of truth. `comparison.md` is
regenerated from those JSONs by `python -m benchmarks.render_report`,
so a third-party reviewer can re-render a year-old run without
re-spending the credits.

## Pre-launch state

This directory is empty until someone with API keys runs the
harness. The first public report will be tagged
`benchmarks-2026-Q2`.

## Reproducibility contract

Every artefact in a results directory is reproducible from
`manifest.json` + the git SHA the harness recorded. Run:

```bash
git checkout <git_sha_from_manifest>
python -m benchmarks.harness --seed <seed_from_manifest>
```

…on a machine with the same provider keys to recreate the numbers
within statistical noise (wall time + 5%, cost ≤ 1¢, factual_score
within ±2 on the 0-100 scale per the inter-rater study).
