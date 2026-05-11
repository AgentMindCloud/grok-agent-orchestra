<h1 align="center">Grok Agent Orchestra</h1>

<p align="center">
  <b>Multi-agent research with visible debate and enforceable safety vetoes — powered by Grok.</b>
</p>

<p align="center">
  <a href="https://github.com/agentmindcloud/grok-build-bridge"><img alt="Requires Build Bridge" src="https://img.shields.io/badge/requires-grok--build--bridge-ff6b35?style=flat-square" /></a>
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=flat-square&logo=python&logoColor=white" /></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache%202.0-00C2A8?style=flat-square" /></a>
  <a href="https://agentmindcloud.github.io/grok-agent-orchestra/"><img alt="Docs" src="https://img.shields.io/badge/docs-mkdocs--material-FF6B35?style=flat-square&logo=read-the-docs&logoColor=white" /></a>
  <a href="https://github.com/agentmindcloud/grok-agent-orchestra/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/agentmindcloud/grok-agent-orchestra?style=flat-square&logo=github" /></a>
</p>

> **⚠ Requires [Grok Build Bridge](https://github.com/agentmindcloud/grok-build-bridge).**
> Agent Orchestra is a Bridge add-on — it shares Bridge's `XAIClient`,
> safety primitives, and the combined-runtime hooks. Install Bridge
> first; Orchestra imports raise `RuntimeError` with a clear hint if
> Bridge is missing. See
> [docs/integrations/build-bridge.md](docs/integrations/build-bridge.md)
> for the full pairing guide (Mode A: Bridge-led, Mode B: Orchestra-led).

<p align="center">
  <img src="docs/images/hero.svg" alt="Agent Orchestra — pick a template, watch Grok / Harper / Benjamin debate in role-coloured lanes while Lucas adjudicates from the judge bench, then download the citation-rich report." width="780" />
</p>

<p align="center">
  <em>Hero is a branded SVG illustration — real screenshots replace it post-launch when <code>scripts/capture-demo.mjs</code> runs against a live stack. The Rich-TUI mockup lives at <code>docs/images/tui-demo.svg</code>.</em>
</p>

---

## Why Agent Orchestra?

- **Visible debate, not a black box.** Four named roles (Grok, Harper, Benjamin, Lucas) argue on screen. Every turn, every tool call, every reasoning gauge streams into a Rich TUI you can actually read while it happens.
- **Lucas veto = enforceable quality / safety gate.** A separate `grok-4.20-0309` pass with strict-JSON output, high reasoning effort, and *fail-closed* defaults. Malformed, low-confidence, or timed-out → exit code 4 → nothing ships.
- **Native Grok multi-agent endpoint as power mode.** Today: drive `grok-4.20-multi-agent-0309` directly (4 or 16 agents) *or* run a prompt-simulated debate from the same YAML. Bring your own key from any provider via the LiteLLM adapter — same orchestration, your choice of engine.
- **Bridge-paired by design.** The combined runtime (`combined: true`) drives Bridge's generate → scan → Orchestra's debate → Lucas veto → Bridge's deploy in one TUI. The lighter Mode A drops a single `safety.lucas_veto_enabled: true` line into a Bridge YAML and Lucas gates the deploy.

## Three-tier capability matrix

Pick the tier that matches what you have on hand right now. `grok-orchestra doctor` will tell you which tiers your machine has configured.

| Tier | Setup | Cost | Quality | Best for |
| --- | --- | --- | --- | --- |
| **Demo mode** | Bridge installed; canned event streams | Bridge-side cost only | Pre-canned, deterministic | First five minutes; demos; replaying a fixture run |
| **Local mode** (Ollama) | Bridge + `ollama pull llama3.1:8b` + `pip install 'grok-agent-orchestra[adapters]'` | LLM cost only — no SaaS layer | Solid for drafts; below cloud frontier | Privacy-sensitive runs; offline iteration |
| **Cloud mode** (BYOK) | Bridge + `XAI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Pay-as-you-go (your invoice) | Ship-grade | Production research, customer-facing reports |

Capabilities by tier:

| Capability | Demo | Local | Cloud |
| --- | :---: | :---: | :---: |
| Visible 4-role debate (Grok / Harper / Benjamin / Lucas) | ✅ canned | ✅ real | ✅ real |
| Live debate streaming in the TUI / web UI | ✅ | ✅ | ✅ |
| Lucas veto (fail-closed safety gate) | ✅ canned verdicts | ✅ runs on local LLM | ✅ runs on Grok / Claude |
| Per-role model overrides (`agents[].model`) | n/a | ✅ Ollama pins | ✅ any provider |
| Live web research via Tavily | n/a | 🟡 BYOK Tavily key | ✅ |
| Native Grok multi-agent endpoint (one streamed call) | n/a | n/a | ✅ Grok-only runs |
| Citations + Markdown / PDF / DOCX export | ✅ | ✅ | ✅ |

Honest tradeoffs:

- **Demo mode** uses pre-canned event streams. It's the right path to learn the framework's vocabulary in five minutes, but it won't answer real research questions — every run produces the same canned text shape.
- **Local mode** swaps in a real LLM, but `llama3.1:8b` is materially below `claude-3-5-sonnet` / `grok-4.20` on long-context synthesis. The visible debate + Lucas veto still keep failure modes loud — the *reasoning quality* tracks the model.
- **Cloud mode** is the production path. Mixing a cloud-grade Lucas with a local Harper is a pragmatic middle ground (`mode_label="mixed"` in the run summary).

Bridge sits underneath every tier — Orchestra never bypasses it. Run `grok-orchestra doctor` to see which tiers your machine has live right now.

## Benchmarks

Agent Orchestra ships a public head-to-head benchmark harness at
[`benchmarks/`](benchmarks/) that runs every system-under-test
against a 12-goal corpus across four domains, scored by an
independent third-party LLM-as-judge (default
`anthropic/claude-sonnet-4-6` — never Lucas, never Grok). The
methodology is locked in [`benchmarks/methodology.md`](benchmarks/methodology.md);
the recurring CI workflow at [`.github/workflows/benchmarks.yml`](.github/workflows/benchmarks.yml)
re-runs monthly + on every release tag and opens a PR with the
fresh `comparison.md` for human review.

```bash
pip install -e .
pip install "litellm>=1.40,<2" "gpt-researcher>=0.10,<2" pyyaml matplotlib
export XAI_API_KEY=...     OPENAI_API_KEY=...
export TAVILY_API_KEY=...  ANTHROPIC_API_KEY=...
python -m benchmarks.harness                     # full matrix
python -m benchmarks.harness --skip-judge        # cheap metrics only
```

Round 1 numbers land in [`benchmarks/results/latest.md`](benchmarks/results/) (and
auto-include into [`docs/architecture/comparison.md`](docs/architecture/comparison.md))
the next time the workflow lands a green run with the keys configured.
We don't suppress losing rows — the per-goal table publishes every
row, including the goals where GPT-Researcher beats Orchestra.

What we measure: tokens, dollar cost, wall time, citations + unique
domains, audit lines per dollar (Orchestra's structural advantage),
factual score against curated reference bullets, hallucination
rate (claims without supporting citation in a ±2-sentence window),
plus a manual "did the judge agree with the Lucas veto?" review
when one fires. See the methodology for the full rubric + the
inter-rater calibration study.

## Use from Claude

Agent Orchestra ships a [Claude Skill](https://github.com/agentmindcloud/grok-agent-orchestra/tree/main/skills/agent-orchestra)
at `skills/agent-orchestra/`. Drop it into Claude Code and Claude can
invoke a multi-agent run when the user asks for deep research,
debate, red-teaming, due diligence, competitor briefs, paper
summaries, or news digests.

```bash
# Personal install (every project, every session)
mkdir -p ~/.claude/skills && cp -R skills/agent-orchestra ~/.claude/skills/

# Project-scoped install (commit alongside your code)
mkdir -p .claude/skills && cp -R skills/agent-orchestra .claude/skills/
```

The skill auto-detects two transport modes: it spawns the local
`grok-orchestra` CLI when `pip install grok-agent-orchestra` is
present, or `POST`s to a remote FastAPI when
`AGENT_ORCHESTRA_REMOTE_URL` is set. Local wins when both are
available — no network, no auth, no token-budget surprises.

Inside Claude, just describe the task:

> "Do a deep competitive analysis of agent frameworks in 2026."
>
> "Red-team this product launch plan: …"
>
> "Summarise this arXiv paper: <link>"

Full setup guide: **[docs/integrations/claude-skill.md](docs/integrations/claude-skill.md)**.

## Use in VS Code

A first-party [VS Code extension](extensions/vscode/) lives at
`extensions/vscode/`. Right-click any YAML, run **Agent Orchestra: Run
current YAML**, and watch the role-coloured debate stream in a
side-panel webview while the Lucas judge bench tracks the verdict.

**Marketplace publishing is intentionally disabled until a v1.x
release** — install from a local `.vsix` build:

```bash
cd extensions/vscode
npm install
npm run package
npm run vsce:package          # → agent-orchestra.vsix
code --install-extension agent-orchestra.vsix
```

The extension shares the wire contract with the Claude Skill. It
auto-detects `grok-orchestra` on PATH (preferred) or falls back to
the FastAPI at `agentOrchestra.serverUrl`. Schema-aware completions
trigger inside `*.orchestra.yaml`; bundled snippets cover the canonical
patterns (`orchestra:native`, `orchestra:debate-loop`,
`orchestra:deep-research`, `orchestra:web`, `orchestra:mcp`,
`orchestra:veto`).

Full guide: **[docs/integrations/vscode.md](docs/integrations/vscode.md)**.

## Quickstart

Pick the install path that fits your situation. They produce the same `grok-orchestra` CLI.

### From GitHub (today)

Bridge first, Orchestra second — Orchestra raises a friendly
`RuntimeError` at import time if Bridge isn't on `PYTHONPATH`:

```bash
pip install git+https://github.com/agentmindcloud/grok-build-bridge.git
pip install git+https://github.com/agentmindcloud/grok-agent-orchestra.git
```

### From PyPI (when both ship)

Both packages are on the alpha → 0.2 → 1.0 path. The day Bridge
publishes to PyPI, the install becomes:

```bash
pip install grok-build-bridge   # Bridge first
pip install grok-agent-orchestra
```

Until then the GitHub install above is the supported path. The
[Build Bridge pairing guide](docs/integrations/build-bridge.md)
covers troubleshooting.

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

### Run in Docker

The fastest path to a working dashboard — no Python install on the host. Pre-built multi-arch images (linux/amd64 + linux/arm64) are published to **GitHub Container Registry**:

```bash
docker pull ghcr.io/agentmindcloud/grok-agent-orchestra:latest
docker run --rm -p 8000:8000 \
  -e XAI_API_KEY=<your-key> \
  ghcr.io/agentmindcloud/grok-agent-orchestra:latest
# → http://localhost:8000
```

Pin a specific version in production — `:latest` is fine for evals, but production should track an explicit version tag so the image you ship in CI matches what you smoke-tested. The first published image will be tagged `:v0.1.0` to match the source release.

Or build + run from a fresh clone with `docker compose`:

```bash
git clone https://github.com/agentmindcloud/grok-agent-orchestra.git
cd grok-agent-orchestra
cp .env.example .env                  # paste XAI_API_KEY (optional for simulated runs)
docker compose up --build
```

For hot-reload during development:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

Smoke-test a fresh build end-to-end (bash + PowerShell variants ship side by side):

```bash
./scripts/docker-smoke-test.sh                  # macOS / Linux
.\scripts\docker-smoke-test.ps1                 # Windows
```

The image binds to `0.0.0.0:8000` by default, runs as the unprivileged `orchestra` user, and ships a `/api/health` HEALTHCHECK so `docker ps` reports container readiness.

### Web research

When a YAML spec carries a `sources:` block, Orchestra runs a real research pass before Harper starts thinking. Findings are prepended to the goal as a "Web research findings" block, and the underlying URLs become Citations on the published report.

```bash
pip install 'grok-agent-orchestra[search]'
export TAVILY_API_KEY=tvly-...
grok-orchestra serve --no-browser
# pick `weekly-news-digest`, untoggle Simulated, click Run.
```

YAML shape (defaults shown):

```yaml
sources:
  - type: web
    provider: tavily              # default; bring your own via @register_provider
    max_results_per_query: 5
    fetch_top_k: 5
    allow_js: false               # set true to use Playwright fallback (extra: [js])
    allowed_domains: []           # empty = all
    blocked_domains: ["pinterest.com", "quora.com"]
    cache_ttl_seconds: 3600       # SQLite cache in $GROK_ORCHESTRA_WORKSPACE/.cache/web/
    budget:
      max_searches: 20
      max_fetches: 50
```

Honourable mentions:

- `robots.txt` is fail-closed for explicit Disallow rules and fail-open on transient network errors. The user-agent is `grok-agent-orchestra/<version> (+repo URL)` so site operators can policy us.
- The fetcher caches **extracted text + metadata** only — never raw HTML — so disk usage stays sane even on long-running services.
- Per-run **budget** caps prevent runaway spend; over-spend raises `SourceBudgetExceeded` with a clear message rather than silently degrading.
- Set `simulated: true` on the run (the dashboard's default) and the search + fetch stages serve canned data — no API key, no network — ideal for demos and tests.
- The dashboard renders a "🌐 Searching the web…" panel above the role lanes with the query, the hits, and the fetched titles so the user can audit Harper's source set.

JS-rendered pages are an opt-in extra (`pip install 'grok-agent-orchestra[js]'` — adds Playwright + Chromium, ~300 MB). When enabled, pages whose extracted text falls below a threshold get re-fetched through Playwright; the same fetcher caches the result.

### Pluggable LLMs (BYOK)

**Grok = power mode. Other providers = portability mode.**

When every role uses a Grok model (the default), Orchestra routes through the native multi-agent endpoint — one streamed call, four agents, full TUI. When a role pins a non-Grok model, the same orchestration runs through a LiteLLM-backed adapter so you can swap in OpenAI, Anthropic, Ollama, Mistral, Bedrock, Azure, Together, Groq, … without touching the framework.

```bash
pip install 'grok-agent-orchestra[adapters]'
# Bring your own keys — set whichever providers your YAML pins:
export OPENAI_API_KEY=<paste-yours-here>
export ANTHROPIC_API_KEY=<paste-yours-here>
```

Per-role model overrides:

```yaml
model: anthropic/claude-3-5-sonnet     # global default for the run

orchestra:
  agents:
    - {name: Grok,     role: coordinator}
    - {name: Harper,   role: researcher, model: openai/gpt-4o}
    - {name: Benjamin, role: logician}
    - {name: Lucas,    role: contrarian, model: grok-4.20-0309}  # judge stays on Grok

# Optional aliases — name your own.
model_aliases:
  fast:    openai/gpt-4o-mini
  premium: anthropic/claude-3-5-sonnet
```

The runtime auto-detects the run's mode and surfaces it on `OrchestraResult.mode_label`:

| `mode_label` | When | What happens |
| --- | --- | --- |
| `native` | Every role uses a Grok model AND pattern is `native` | Multi-agent endpoint — fastest path. |
| `simulated` | Every role uses a Grok model on a non-`native` pattern (hierarchical / debate-loop / …) | Per-role debate over `grok-4.20-0309`. |
| `adapter` | Every role uses a non-Grok model | Per-role debate over the LiteLLM adapter. |
| `mixed` | Some Grok, some non-Grok | Per-role debate; each role hits its own provider. |

Cost tracking is on the run-detail panel: `provider_costs` carries a per-provider USD breakdown derived from `litellm.cost_per_token`. The Grok-native path isn't priced (no public unit cost available).

CLI helpers:

```bash
grok-orchestra models list                                       # show defaults + roles + aliases
grok-orchestra models list --spec ./my-spec.yaml                 # …including spec-defined aliases
grok-orchestra models test --model openai/gpt-4o-mini            # tiny BYOK connectivity check
grok-orchestra models test --model anthropic/claude-3-5-sonnet
```

`models test` reads the matching `*_API_KEY` from the environment via LiteLLM's resolver — the framework never embeds, ships, or logs the value. A missing key surfaces a clear "set OPENAI_API_KEY" hint, not a stack trace.

### Observability (BYOK, off by default)

Tracing is **opt-in**. The framework ships with a zero-overhead `NoOpTracer` so unset runs are byte-for-byte identical to the no-tracing path. Set ONE of these env vars to enable a backend:

| Backend | Activator env var(s) |
| --- | --- |
| **LangSmith** (primary) | `LANGSMITH_API_KEY` (+ optional `LANGSMITH_PROJECT`, `LANGSMITH_SAMPLE_RATE`) |
| **OTLP** (Jaeger / Tempo / Honeycomb / …) | `OTEL_EXPORTER_OTLP_ENDPOINT` |

```bash
pip install 'grok-agent-orchestra[tracing]'
export LANGSMITH_API_KEY="<paste-your-key-here>"
grok-orchestra trace info       # confirm the backend selected
grok-orchestra trace test       # emit a synthetic two-span run + print the deep-link
```

Every run produces a span tree:

```
run → debate_round_N → role_turn (per role) → llm_call / tool_call
                    → lucas_evaluation → veto_decision
   → publisher → markdown_render / pdf_render / docx_render
```

When a backend is active, the dashboard's run-detail panel grows a **🔭 View trace** button that deep-links to the LangSmith / Langfuse run.

**Scrubber.** Every span passes through `grok_orchestra.tracing.scrubber` before it leaves the box. Credential-shaped strings (`sk-…`, `tvly-…`, `Bearer …`, AWS / GCP keys, …) and sensitive field names (`Authorization`, `*_API_KEY`, `*_SECRET_KEY`, `*_TOKEN`) are redacted in-place; long strings are truncated to 4 KiB. Backends never see a raw key.

![LangSmith trace](docs/images/trace-langsmith.svg)

Full reference: [`docs/observability.md`](docs/observability.md).

### Inline images in reports (BYOK)

Reports can carry an auto-generated cover + section illustrations. Default OFF; opt in per-template:

```yaml
publisher:
  images:
    enabled: true
    provider: flux              # grok (stub today) | flux
    budget: 4                   # max images per run
    cover: true
    section_illustrations: 2
    style: "minimal flat illustration, no faces"
```

```bash
pip install 'grok-agent-orchestra[adapters,publish,images]'
export REPLICATE_API_TOKEN="<paste-yours-here>"
grok-orchestra run examples/with-images/illustrated-research.yaml
```

What ships:

- Each PNG lands at `$GROK_ORCHESTRA_WORKSPACE/runs/<run-id>/images/`.
- The Markdown report references them with relative paths
  (`![…](images/cover.png)`).
- The PDF (WeasyPrint) resolves them via `base_url`.
- The DOCX (python-docx) embeds them inline at the top of each section.
- The dashboard's run-detail panel grows a thumbnail gallery linked to
  the per-image URLs at `/api/runs/{id}/images/{name}.png`.

Honest tradeoffs:

- **Grok image API isn't publicly available yet.** `provider: grok` is a
  placeholder that fails loud with an actionable hint to switch to
  `flux`. The day xAI ships, the same YAML field flips over silently.
- **Flux schnell costs ~$0.003/image** (your Replicate invoice). The
  budget cap stops the run cleanly when reached. A SHA-keyed on-disk
  cache makes re-runs free.
- **Policy-refused prompts** (real public figures, copyrighted
  characters, an extensible deny-list) skip that one image with a
  WARNING; the report still ships.
- **Tracing**: every image emits an `image_generation` span with
  `provider`, `model`, `cache_key`, `cost_usd` so LangSmith /
  Langfuse / OTel can index by spend.

Full template + setup checklist: [`examples/with-images/`](examples/with-images/).

### Reports

Every dashboard run auto-writes a structured Markdown report and a `run.json` snapshot to `$GROK_ORCHESTRA_WORKSPACE/runs/<run-id>/`. PDF and DOCX render lazily on first download. To enable PDF/DOCX install the `[publish]` extra:

```bash
pip install 'grok-agent-orchestra[publish]'
```

WeasyPrint (used for the PDF render) needs **Cairo** and **Pango** on the host. The Docker image bundles them. On bare-metal:

| Host | Install |
| --- | --- |
| macOS | `brew install cairo pango libffi` |
| Debian / Ubuntu | `sudo apt-get install libcairo2 libpango-1.0-0 libpangoft2-1.0-0 libffi8 libgdk-pixbuf-2.0-0 fonts-liberation` |
| Fedora / RHEL | `sudo dnf install cairo pango libffi gdk-pixbuf2 liberation-fonts` |
| Windows | Easiest path: use the Docker image. WeasyPrint also publishes [native instructions](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows). |

Export from the CLI after a dashboard run completes:

```bash
grok-orchestra export <run-id> --format=all --output=./reports
```

Or pull straight from the running server:

```bash
curl -O http://localhost:8000/api/runs/<run-id>/report.md
curl -O http://localhost:8000/api/runs/<run-id>/report.pdf
curl -O http://localhost:8000/api/runs/<run-id>/report.docx
```

The PDF carries a cover page with a confidence meter (Lucas's verdict score) and footnoted citations. The DOCX uses Word's built-in `Heading 1` / `List Number` styles so the TOC field works without manual fixing.

![Report sample](docs/images/report-sample.svg)

### Web UI

Optional dashboard with live WebSocket-streamed debates. Install the `[web]` extra and run:

```bash
pip install 'grok-agent-orchestra[web]'
grok-orchestra serve              # → opens http://127.0.0.1:8000
grok-orchestra serve --no-browser # CI / headless
```

Pick a template from the left rail, leave **Simulated** on for an offline demo, and click **Run** — Grok / Harper / Benjamin / Lucas appear as colour-coded lanes with streaming tokens, then Lucas's verdict banner, then the final output card.

![Web UI dashboard](docs/images/web-ui.svg)

The dashboard exposes a small JSON API (`/api/templates`, `/api/run`, `/api/runs/{id}`, `/ws/runs/{id}`); see [`grok_orchestra/web/main.py`](grok_orchestra/web/main.py) for the contract. State is in-memory and the server binds to `127.0.0.1` by default — production needs persistence (Redis/SQLite) and auth, neither of which ships in v1.

#### Modern frontend (Next.js 14)

A production-grade dashboard lives under [`frontend/`](frontend/) — Next.js 14 (App Router) + Tailwind + shadcn/ui, with a typed API client and a WebSocket hook with auto-reconnect. The classic single-file dashboard remains available at `/classic/` as a fallback.

![Courtroom view](docs/images/web-ui-modern.svg)

```bash
cd frontend
cp .env.example .env.local
pnpm install
pnpm dev                      # → http://localhost:3000
```

In a separate terminal, run the FastAPI backend (`grok-orchestra serve --no-browser`). CORS for `http://localhost:3000` is on by default; override with `GROK_ORCHESTRA_CORS_ORIGINS=...`.

For Docker, the main `docker compose up` continues to expose port 8000 with the v1 dashboard. To run the Next.js dev server alongside, use the dev overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
# → http://localhost:8000  (FastAPI)
# → http://localhost:3000  (Next.js dev)
```

A future production image will ship the Next.js static export pre-baked at `/`. The courtroom-view illustration above lives at [`docs/images/web-ui-modern.svg`](docs/images/web-ui-modern.svg).

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

The CLI ships **18 certified templates** in [`grok_orchestra/templates/`](grok_orchestra/templates/), with a machine-readable catalog at [`INDEX.yaml`](grok_orchestra/templates/INDEX.yaml). Discover, inspect, copy, and run them via the `templates` command group:

```bash
grok-orchestra templates list                          # all 18, grouped by category
grok-orchestra templates list --tag business           # filter by tag
grok-orchestra templates list --format json            # machine-readable
grok-orchestra templates show competitive-analysis     # print the YAML
grok-orchestra templates copy red-team-the-plan ./my.yaml
grok-orchestra dry-run red-team-the-plan               # offline, no API key
grok-orchestra run red-team-the-plan                   # live (needs XAI_API_KEY)
```

| Template | Pattern | Tags | What it does |
| --- | --- | --- | --- |
| [`orchestra-native-4`](grok_orchestra/templates/orchestra-native-4.yaml) | native | research · fast · web-search | Daily 3-tweet X-thread on the native 4-agent endpoint. |
| [`orchestra-native-16`](grok_orchestra/templates/orchestra-native-16.yaml) | native | research · deep · web-search | Weekly deep-research thread, 16 agents at high effort. |
| [`orchestra-simulated-truthseeker`](grok_orchestra/templates/orchestra-simulated-truthseeker.yaml) | native | debate · research | Visible Grok / Harper / Benjamin / Lucas fact-check debate. |
| [`orchestra-hierarchical-research`](grok_orchestra/templates/orchestra-hierarchical-research.yaml) | hierarchical | research · deep · debate · web-search | Two-team hierarchy: Research → Critique → Synthesis. |
| [`orchestra-dynamic-spawn-trend-analyzer`](grok_orchestra/templates/orchestra-dynamic-spawn-trend-analyzer.yaml) | dynamic-spawn | research · fast · web-search | Concurrent fan-out — Harper+Lucas mini-debates in parallel. |
| [`orchestra-debate-loop-policy`](grok_orchestra/templates/orchestra-debate-loop-policy.yaml) | debate-loop | debate · deep | Iterate up to 5 rounds toward a balanced 280-char summary. |
| [`orchestra-parallel-tools-fact-check`](grok_orchestra/templates/orchestra-parallel-tools-fact-check.yaml) | parallel-tools | research · fast · debate · web-search | Per-agent tool routing with off-list audit. |
| [`orchestra-recovery-resilient`](grok_orchestra/templates/orchestra-recovery-resilient.yaml) | recovery | research · deep · web-search | Native-16 wrapped with rate-limit fallback + retry. |
| [`combined-trendseeker`](grok_orchestra/templates/combined-trendseeker.yaml) | native (combined) | business · research · web-search | Bridge codegen → Orchestra debate → Lucas veto → deploy. |
| [`combined-coder-critic`](grok_orchestra/templates/combined-coder-critic.yaml) | native (combined) | technical · debate | Bridge generates a TypeScript CLI; Orchestra critiques the code. |
| [`deep-research-hierarchical`](grok_orchestra/templates/deep-research-hierarchical.yaml) | hierarchical | research · deep · debate · web-search | Recursive 3-deep sub-question generation with per-level veto. |
| [`debate-loop-with-local-docs`](grok_orchestra/templates/debate-loop-with-local-docs.yaml) 🟡 | debate-loop | research · deep · local-docs · debate | Debate a local PDF/Markdown corpus to consensus. *requires v0.3+.* |
| [`competitive-analysis`](grok_orchestra/templates/competitive-analysis.yaml) | hierarchical | research · business · web-search · debate | Competitor brief; Lucas vetoes any unsourced claim. |
| [`due-diligence-investor-memo`](grok_orchestra/templates/due-diligence-investor-memo.yaml) | hierarchical | business · research · debate | 1-pager memo — public sources, hype-vetoed, ≥ 3 risks enforced. |
| [`red-team-the-plan`](grok_orchestra/templates/red-team-the-plan.yaml) | hierarchical | debate · business · fast | Stress-test a plan from 4 angles. No external research, dry-run-friendly. |
| [`weekly-news-digest`](grok_orchestra/templates/weekly-news-digest.yaml) 🟡 | native | research · web-search · fast | Topic + ISO date range → cited bullet digest. *web-search full in v0.3+.* |
| [`paper-summarizer`](grok_orchestra/templates/paper-summarizer.yaml) | hierarchical | research · technical · deep | arXiv / PDF → Problem · Method · Results · Limitations · Next. |
| [`product-launch-brief`](grok_orchestra/templates/product-launch-brief.yaml) | hierarchical | business · fast | Launch brief — positioning, audience, channels, risks (≥ 3), KPIs. |

🟡 = uses a roadmap-only feature that is stubbed today; see the file's `requires v0.3+` note.

## Roadmap

Grouped by theme. Status emojis: ✅ shipped · 🟡 in progress · ⏳ planned.

- **Distribution** — 🟡 PyPI publish (paired with Bridge release) · ⏳ Docker image · ⏳ Homebrew tap.
- **Adapters** — ⏳ provider adapter layer (OpenAI / Anthropic / local) so the same YAML targets non-Grok engines.
- **Knowledge** — ⏳ local docs ingest with citation-preserving retrieval · ⏳ structured corpus templates.
- **Surfaces** — ✅ web UI with live WebSocket debate stream · ⏳ exportable HTML transcripts · ⏳ Slack-style notifier hooks.
- **Veto depth** — ⏳ pluggable veto stacks (legal / brand / PII gates chained before Lucas) · ⏳ veto replay tooling.
- **Reliability** — ✅ recovery pattern w/ fallback model · ⏳ richer cost/latency budgets · ⏳ distributed run mode.

The 18-item improvement roster lives in [`docs/`](docs/) — each item resolves into one of the themes above.

## Documentation

Full docs ship at **<https://agentmindcloud.github.io/grok-agent-orchestra/>** —
MkDocs Material with versioned slots, auto-deployed by `.github/workflows/docs.yml`:

- `/latest/` — most recent release tag.
- `/dev/` — rolling, refreshed on every push to `main`.
- `/<vX.Y.Z>/` — archived per-version slots.

Local preview:

```bash
pip install -e ".[docs-build]"
mkdocs serve
# → http://127.0.0.1:8000
```

Highlights:
[Quickstart](https://agentmindcloud.github.io/grok-agent-orchestra/getting-started/quickstart/) ·
[Templates](https://agentmindcloud.github.io/grok-agent-orchestra/guides/templates/) ·
[Architecture](https://agentmindcloud.github.io/grok-agent-orchestra/architecture/overview/) ·
[Lucas veto](https://agentmindcloud.github.io/grok-agent-orchestra/concepts/lucas-veto/) ·
[CLI reference](https://agentmindcloud.github.io/grok-agent-orchestra/reference/cli/).

## Contributing

Issues, PRs, and template submissions welcome. See the
[Contributing guide](https://agentmindcloud.github.io/grok-agent-orchestra/contributing/)
for the full flow. Short version:

1. Open an issue before large changes so we can sanity-check the design against the veto invariants.
2. Run `pytest` and `ruff check .` before pushing — CI enforces ≥85% coverage and the lint suite.
3. New CLI flags? Re-run `python scripts/gen_cli_docs.py` so the docs site stays current.

## License & Attribution

Apache 2.0 — see [`LICENSE`](LICENSE). Use it, fork it, ship it. Lucas still has to sign off.

Built on top of [`grok-build-bridge`](https://github.com/agentmindcloud/grok-build-bridge) and the [xAI SDK](https://docs.x.ai/). Inspired in spirit by [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher); the [`benchmarks/`](benchmarks/) harness runs head-to-head once API keys are configured.
