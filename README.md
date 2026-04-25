<h1 align="center">Grok Agent Orchestra</h1>

<p align="center">
  <b>Multi-agent research with visible debate and enforceable safety vetoes — powered by Grok.</b>
</p>

<p align="center">
  <a href="https://pypi.org/project/grok-agent-orchestra/"><img alt="PyPI" src="https://img.shields.io/badge/pypi-coming%20in%20v0.1.0-C026D3?style=flat-square" /></a>
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=flat-square&logo=python&logoColor=white" /></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache%202.0-00C2A8?style=flat-square" /></a>
  <a href="#"><img alt="Docker pulls" src="https://img.shields.io/badge/docker-coming%20soon-2496ED?style=flat-square&logo=docker&logoColor=white" /></a>
  <a href="#"><img alt="Discord" src="https://img.shields.io/badge/discord-coming%20soon-5865F2?style=flat-square&logo=discord&logoColor=white" /></a>
  <a href="https://github.com/agentmindcloud/grok-agent-orchestra/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/agentmindcloud/grok-agent-orchestra?style=flat-square&logo=github" /></a>
</p>

<p align="center">
  <img src="docs/images/tui-demo.gif" alt="Rich TUI demo — Grok / Harper / Benjamin / Lucas debate streamed live, ending with a Lucas veto verdict." width="780" />
</p>

---

## Why Agent Orchestra?

- **Visible debate, not a black box.** Four named roles (Grok, Harper, Benjamin, Lucas) argue on screen. Every turn, every tool call, every reasoning gauge streams into a Rich TUI you can actually read while it happens.
- **Lucas veto = enforceable quality / safety gate.** A separate `grok-4.20-0309` pass with strict-JSON output, high reasoning effort, and *fail-closed* defaults. Malformed, low-confidence, or timed-out → exit code 4 → nothing ships.
- **Native Grok multi-agent endpoint as power mode.** Today: drive `grok-4.20-multi-agent-0309` directly (4 or 16 agents) *or* run a prompt-simulated debate from the same YAML. Roadmap: a provider-adapter layer so you can swap engines without touching specs.

## Compared to GPT-Researcher

[gpt-researcher](https://github.com/assafelovic/gpt-researcher) is the reference competitor. Honest scorecard:

| Capability | Grok Agent Orchestra | GPT-Researcher |
| --- | --- | --- |
| Multi-agent debate | ✅ Visible & streamed | ❌ Hidden |
| Safety veto layer | ✅ Lucas (fail-closed) | ❌ |
| Native Grok multi-agent endpoint | ✅ | ❌ |
| Local docs ingest | 🟡 Roadmap | ✅ |
| Web UI | 🟡 Roadmap | ✅ |
| `pip install` from PyPI | ✅ from v0.1.0 | ✅ |

🟡 = on the roadmap, see [Roadmap](#roadmap). We won't claim a checkmark we can't back.

## Quickstart

Pick the install path that fits your situation. They produce the same `grok-orchestra` CLI.

### From PyPI

```bash
pip install grok-agent-orchestra
```

Available from `v0.1.0` onward.

### From GitHub

If you need a tip-of-`main` build before the next release. The sibling [`grok-build-bridge`](https://github.com/agentmindcloud/grok-build-bridge) installs from git too:

```bash
pip install git+https://github.com/agentmindcloud/grok-build-bridge.git
pip install git+https://github.com/agentmindcloud/grok-agent-orchestra.git
```

### Editable / dev install

```bash
git clone https://github.com/agentmindcloud/grok-agent-orchestra.git
cd grok-agent-orchestra
pip install -e ".[dev]"
```

### Verifying your install

```bash
grok-orchestra --version      # → grok-orchestra 0.1.0
grok-orchestra templates      # bundled starter catalog
grok-orchestra --help         # subcommand list
```

Set `XAI_API_KEY` for live runs. For offline previews use `--dry-run` — every template ships with a canned-stream replay client, so you don't need a key to see how a pattern behaves.

## Run your first orchestration

Scaffold a workhorse 4-agent native run from the certified template catalog:

```bash
grok-orchestra init orchestra-native-4 --out my-spec.yaml
```

The minimal `my-spec.yaml` looks like this:

```yaml
name: orchestra-native-4
goal: |
  Draft a 3-tweet X thread on today's most-discussed topic in AI agent
  orchestration. Hook + headline, one piece of evidence, one takeaway.
orchestra:
  mode: native
  agent_count: 4
  reasoning_effort: medium
  orchestration:
    pattern: native
safety:
  lucas_veto_enabled: true
  confidence_threshold: 0.80
deploy:
  target: stdout
```

Then dry-run it (no API key required):

```bash
grok-orchestra run my-spec.yaml --dry-run
```

Expected output (truncated):

```text
┌─ Grok Agent Orchestra · native · 4 agents ──────────────────────────┐
│ phase 1/6  resolve         ✓                                        │
│ phase 2/6  stream debate   ▰▰▰▰▰▰▰▰▱▱  Harper → Benjamin            │
│   Harper:   "Primary source: arXiv:2403.…  [web_search]"            │
│   Benjamin: "Logic check: claim 2 conflates correlation with …"     │
│ phase 3/6  audit           ✓ (no off-list tool calls)               │
│ phase 4/6  Lucas veto      ✅ safe=true · confidence=0.91           │
│ phase 5/6  deploy          stdout                                   │
│ phase 6/6  summary                                                  │
└─────────────────────────────────────────────────────────────────────┘
exit 0
```

A `safe=false` verdict prints a red ⛔ panel and exits 4. Nothing deploys.

## Architecture in 60 seconds

```mermaid
flowchart LR
    G([User goal / YAML]) --> P[Planner<br/>parser + dispatcher]
    P --> D{{Debate loop}}
    D --> H((Harper<br/>research))
    D --> B((Benjamin<br/>critique))
    D --> X((Grok<br/>executive))
    H <-.debate.-> B
    H --> L
    B --> L
    X --> L
    L{{⛔ Lucas veto<br/>strict JSON · fail-closed}}
    L -->|safe=true| O([Output / deploy])
    L -->|safe=false| K([exit 4 · blocked])
```

ASCII fallback if Mermaid isn't rendering for you:

```text
   YAML ──► Planner ──► [ Grok · Harper · Benjamin ]
                         │   ▲   │
                         ▼   │   ▼
                         └─ debate ─┘
                              │
                              ▼
                         Lucas veto  ──► safe? ──► output
                                            │
                                            └► exit 4 (blocked)
```

Five composable patterns sit on top of this core: `hierarchical`, `dynamic-spawn`, `debate-loop`, `parallel-tools`, `recovery`. Each is ≤120 LOC. Each ends at Lucas.

## Templates

The CLI ships ten certified templates in [`grok_orchestra/templates/`](grok_orchestra/templates/) with a machine-readable [`INDEX.yaml`](grok_orchestra/templates/INDEX.yaml) catalog. Five highlights:

- [`orchestra-native-4`](grok_orchestra/templates/orchestra-native-4.yaml) — daily X-thread workhorse on the native 4-agent endpoint.
- [`orchestra-native-16`](grok_orchestra/templates/orchestra-native-16.yaml) — weekly deep-research thread, 16 agents at high effort, auto-degrade on 429s.
- [`orchestra-simulated-truthseeker`](grok_orchestra/templates/orchestra-simulated-truthseeker.yaml) — fully-visible Grok / Harper / Benjamin / Lucas debate over 3 fact-check rounds.
- [`orchestra-debate-loop-policy`](grok_orchestra/templates/orchestra-debate-loop-policy.yaml) — iterate up to 5 rounds toward a balanced 280-char summary, with a mid-loop veto.
- [`combined-trendseeker`](grok_orchestra/templates/combined-trendseeker.yaml) — flagship combined run: Bridge codegen → Orchestra debate → Lucas veto → deploy. Cron-ready.

Browse the rest with `grok-orchestra templates`, or read the catalog at [`grok_orchestra/templates/INDEX.yaml`](grok_orchestra/templates/INDEX.yaml).

## Roadmap

Grouped by theme. Status emojis: ✅ shipped · 🟡 in progress · ⏳ planned.

- **Distribution** — 🟡 PyPI publish (v0.1.0) · ⏳ Docker image · ⏳ Homebrew tap.
- **Adapters** — ⏳ provider adapter layer (OpenAI / Anthropic / local) so the same YAML targets non-Grok engines.
- **Knowledge** — ⏳ local docs ingest with citation-preserving retrieval · ⏳ structured corpus templates.
- **Surfaces** — ⏳ web UI for live debate inspection · ⏳ exportable HTML transcripts · ⏳ Discord bot.
- **Veto depth** — ⏳ pluggable veto stacks (legal / brand / PII gates chained before Lucas) · ⏳ veto replay tooling.
- **Reliability** — ✅ recovery pattern w/ fallback model · ⏳ richer cost/latency budgets · ⏳ distributed run mode.

The 18-item improvement roster lives in [`docs/`](docs/) — each item resolves into one of the themes above.

## Contributing

Issues, PRs, and template submissions welcome. The flow:

1. Read [`docs/getting-started.md`](docs/getting-started.md) and the (placeholder) `CONTRIBUTING.md` — TODO: write the formal contributor guide.
2. Open an issue before large changes so we can sanity-check the design against the veto invariants.
3. Run `pytest` and `ruff check .` before pushing — CI enforces ≥85% coverage and the lint suite.

## License & Attribution

Apache 2.0 — see [`LICENSE`](LICENSE). Use it, fork it, ship it. Lucas still has to sign off.

Built on top of [`grok-build-bridge`](https://github.com/agentmindcloud/grok-build-bridge) and the [xAI SDK](https://docs.x.ai/). Inspired in spirit (and benchmarked against) [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher).
