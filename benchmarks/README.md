# `benchmarks/` — head-to-head harness

This is the harness that produces the public comparison report at
`docs/architecture/comparison.md`. It runs every system-under-test
against the 12-goal corpus in `goals.yaml`, scores the results with
an independent third-party LLM-as-judge, and renders a Markdown
report that the docs site auto-includes.

## Layout

```
benchmarks/
├── goals.yaml             # 12 goals × 4 domains; canonical corpus
├── methodology.md         # locked-in measurement rules
├── harness.py             # python -m benchmarks.harness
├── scoring.py             # pure-function metrics
├── judge.py               # LLM-as-judge (LiteLLM-driven, model-agnostic)
├── render_report.py       # JSON manifest → comparison.md
├── charts.py              # matplotlib SVGs (optional)
├── runners/
│   ├── __init__.py        # registry pattern
│   ├── orchestra.py       # spawns `grok-orchestra run … --json`
│   └── gpt_researcher.py  # async lib wrapper
└── results/
    ├── README.md
    ├── latest.md          # symlink (or copy) → most recent comparison.md
    └── <YYYY-MM>-<seed>/  # one directory per harness run
```

## Quickstart

```bash
# Set the keys the runners need.
export XAI_API_KEY=...                 # for orchestra-grok
export OPENAI_API_KEY=...              # for orchestra-litellm
export TAVILY_API_KEY=...              # both systems share Tavily by default
export ANTHROPIC_API_KEY=...           # for the default judge model

# Cheap, no LLM-as-judge — just the deterministic metrics.
python -m benchmarks.harness --skip-judge --systems orchestra-grok

# Full matrix with the judge.
python -m benchmarks.harness

# Single goal, single system, dry-run print of the plan.
python -m benchmarks.harness \
  --goals tech-agent-frameworks-2026 \
  --systems orchestra-grok \
  --dry-run
```

The harness writes to `benchmarks/results/<YYYY-MM>-<seed>/` and
updates `benchmarks/results/latest.md` so the docs site picks up
the new run automatically. Reproducibility metadata
(`manifest.json`) ships in every result directory.

## Adding a system-under-test

1. Subclass `Runner` in `benchmarks/runners/your_runner.py`.
2. Decorate a factory with `@register("your-runner-slug")`.
3. Import the module from `runners/__init__.py` so the registry
   side-effect fires on `python -m benchmarks.harness`.
4. The harness will run it the next time `--systems` includes its slug.

See `runners/orchestra.py` and `runners/gpt_researcher.py` for the
canonical patterns (subprocess spawn vs async library).

## Adding a goal

Append to `goals.yaml`. Required fields:

```yaml
- id: domain-short-slug
  domain: tech | finance | science | operations
  prompt: |
    Verbatim text passed to every system.
  reference:
    - "First reference bullet (used by the judge for factual_score)"
    - "Second reference bullet"
  expected_format: structured Markdown / 1-page memo / etc.
```

Re-run the harness; the next `comparison.md` will include the new
goal automatically.

## Cadence

The recurring CI workflow at `.github/workflows/benchmarks.yml`
runs the harness on the live PyPI version monthly + on every
release tag, opens a PR with the new `comparison.md`, and includes
the updated SVG charts. PRs review the numbers before they go
public — we never auto-publish.

See `methodology.md` for the locked-in rules (what counts, how the
judge is gated, where Orchestra is allowed to lose).
