# Templates

Agent Orchestra ships **18 certified templates** under `grok_orchestra/templates/`.
Each one is a complete YAML spec that runs unmodified — `grok-orchestra
templates show <slug>` prints the source.

## Browse the catalog

```bash
grok-orchestra templates list                  # every certified template
grok-orchestra templates list --category debate
grok-orchestra templates show red-team-the-plan
grok-orchestra templates init red-team-the-plan ./my-run.yaml
```

## Categories

| Category | Templates |
| --- | --- |
| **Daily / Production** | `orchestra-native-4`, `weekly-news-digest` |
| **Deep research** | `orchestra-native-16`, `deep-research-hierarchical`, `orchestra-hierarchical-research` |
| **Debate / Audit** | `orchestra-simulated-truthseeker`, `orchestra-debate-loop-policy`, `red-team-the-plan` |
| **Fan-out** | `orchestra-dynamic-spawn-trend-analyzer`, `orchestra-parallel-tools-fact-check` |
| **Business** | `competitive-analysis`, `due-diligence-investor-memo`, `product-launch-brief` |
| **Code review** | `combined-coder-critic` |
| **Trend analysis** | `combined-trendseeker` |
| **Resilience** | `orchestra-recovery-resilient` |
| **Local / offline** | `debate-loop-with-local-docs` |
| **Summarisation** | `paper-summarizer` |

## Pick by intent

??? tip "I want to ship a daily X thread"
    `orchestra-native-4` — fast, cheap, production-ready.

??? tip "I want a weekly research report"
    `orchestra-native-16` — premium, rigorous, cited.

??? tip "I want to fact-check one specific claim"
    `orchestra-simulated-truthseeker` — full visible debate, 3 rounds.

??? tip "I want to red-team a draft plan"
    `red-team-the-plan` — no tools, fast, simulated mode.

??? tip "I want to compare N competitors"
    `competitive-analysis` or `orchestra-dynamic-spawn-trend-analyzer`.

??? tip "I'm offline and need privacy-sensitive runs"
    `debate-loop-with-local-docs` — local Ollama + local PDF/MD ingestion.

## Customising a template

```bash
grok-orchestra templates init orchestra-native-4 ./mine.yaml
$EDITOR ./mine.yaml          # tweak goal, providers, tools
grok-orchestra dry-run -f ./mine.yaml
grok-orchestra orchestrate -f ./mine.yaml
```

Every template validates against the YAML schema — `grok-orchestra
validate -f ./mine.yaml` flags drift.

## Contributing a template

1. Drop a new YAML into `grok_orchestra/templates/<slug>.yaml`.
2. Add an entry to `grok_orchestra/templates/INDEX.yaml`.
3. Add it to `tests/test_templates_certified.py` so `mode`, `pattern`,
   and `combined` flags are locked.
4. Open a PR with a screenshot of `grok-orchestra dry-run` output.

See [Contributing → Overview](../contributing/index.md) for the full flow.
