# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Pluggable LLM providers via LiteLLM (BYOK).** New
  ``grok_orchestra.llm`` module exposes an ``LLMClient`` Protocol +
  provider-neutral ``ChatChunk`` / ``ChatResponse`` / ``ToolCall`` /
  ``Usage`` dataclasses. ``GrokNativeClient`` wraps the existing
  ``OrchestraClient`` (zero-overhead delegation — the Grok-native fast
  path is unchanged); ``LiteLLMClient`` lazy-imports ``litellm`` for
  every other provider (OpenAI / Anthropic / Ollama / Bedrock / Azure
  / Together / Groq / …). New ``[adapters]`` extra pulls in
  ``litellm>=1.34``; the package never embeds keys and reads every
  credential from env via LiteLLM's own resolver.
- **YAML model overrides** — top-level ``model:`` sets a global
  default; ``orchestra.agents[].model`` pins per-role; alternative
  ``orchestra.roles.<name>.model`` shape is also accepted; YAML-level
  ``model_aliases:`` map (e.g. ``fast → openai/gpt-4o-mini``) resolves
  with cycle protection. Schema's ``AgentMeta`` gains an optional
  ``model`` field.
- **Mode detection.** ``OrchestraResult`` gains ``mode_label``
  (``native`` / ``simulated`` / ``adapter`` / ``mixed``) plus
  ``role_models`` + per-provider ``provider_costs`` (USD,
  via ``litellm.cost_per_token``). The dispatcher coerces
  ``pattern: native`` to the simulated runtime when any role pins a
  non-Grok model so the multi-agent endpoint is never invoked
  off-Grok.
- **`grok-orchestra models list / test` CLI** — ``list`` shows
  the framework default + spec-defined aliases + per-role pins;
  ``test --model=…`` issues a tiny BYOK connectivity check.
  Friendly install / env-var hints when the credential is missing;
  raw key values are never logged.
- **37 new tests** — ``tests/test_llm_resolution.py`` (model-string
  routing, alias chains + cycles, per-role overrides, mode
  detection), ``tests/test_litellm_adapter.py`` (mocked
  ``litellm.completion`` covering streaming, usage + cost capture,
  provider inference, auth-failure → friendly error, missing-extra →
  install hint), ``tests/test_grok_native_preserved.py`` (all-Grok
  config still routes to ``run_native_orchestra`` — anti-regression
  for the fast path), ``tests/test_mixed_mode.py`` (mixed-provider
  end-to-end, per-provider cost breakdown, all-adapter run reports
  ``mode_label="adapter"``).

### Added
- **Real web research via Tavily.** A new `sources:` YAML block runs a
  citation-ready research pass *before* the orchestration starts;
  findings are prepended to the goal as a "Web research findings" block
  and the underlying URLs land in `run.citations` so the published
  report carries proper attribution. New module
  `grok_orchestra.sources` exposes `Source`, `Document`, `SearchHit`,
  `FetchedPage`, `ResearchResult` plus a pluggable
  `SearchProvider` registry. Default provider:
  `TavilyProvider` (reads `TAVILY_API_KEY`); `SerpAPIProvider`,
  `BingProvider`, `BraveProvider` ship as skeletons with explicit
  `TODO(prompts-9+)` markers.
- **HTTP fetcher** — `httpx` + `trafilatura` (main-content extraction)
  + `selectolax` (title), with a `ThreadPoolExecutor` for bounded
  concurrency, a 15-second per-page timeout, and a UA string that
  identifies the project + version + repo. Domain allow/blocklists,
  `robots.txt` (fail-open on network errors, fail-closed on explicit
  Disallow), SQLite cache (`$GROK_ORCHESTRA_WORKSPACE/.cache/web/`,
  TTL 1h, stores extracted text + metadata only), and per-run budget
  tracking (default 20 searches / 50 fetches). Over-spend raises a
  `SourceBudgetExceeded` with a clear message.
- **Optional `[js]` extra** (`playwright`, ~300 MB) wires a
  PlaywrightFetcher fallback for sites whose extracted text falls
  below 1000 chars — opt-in per-source via `allow_js: true`.
- **`[search]` extra** — `tavily-python`, `httpx`, `selectolax`,
  `trafilatura`. Required for live web research; simulated mode
  works without it. Added to `dev` so tests run end-to-end (Tavily
  client is mocked; `selectolax` + `trafilatura` exercised for real).
- **New event types** — `web_search_started`,
  `web_search_results`, `fetch_started`, `fetch_completed`. The
  dashboard renders them in a "🌐 web activity" panel above the
  role lanes with hits + fetched titles + cache hits.
- **Run-level telemetry** — `Run` carries `citations` and
  `source_stats` lists; both surface on `/api/runs/{id}` and the run
  detail panel. `source_stats` includes `searches`, `fetches`,
  `cache_hits`, `cache_misses`, and the per-run caps.
- **`weekly-news-digest` template** — bumped to v1.0.0; the
  `requires v0.3+` banner is gone, the YAML now carries a real
  `sources:` block (Tavily, blocklists `pinterest.com` /
  `quora.com`).
- **Tests** — `tests/test_tavily_provider.py` (5 tests, mocked
  Tavily client + registry check), `tests/test_fetcher.py` (5
  tests covering extraction, cache, dedupe, allowlist /
  blocklist), `tests/test_robots.py` (3 tests covering deny / fail-
  open / end-to-end refuses to fetch), `tests/test_budget.py` (4
  tests including thread-safe concurrent spends), and
  `tests/test_web_e2e_simulated.py` (4 tests on the simulated full
  run lifecycle, ws event types, and citations in the published
  Markdown).
- **README "Web research" section** with the YAML reference,
  comparison-table tick, robots / cache / budget defaults, and the
  simulated-mode demo path.

### Added
- **Publisher / report export.** Every run that completes via the
  dashboard now auto-writes a canonical `report.md` plus a
  `run.json` snapshot to
  `$GROK_ORCHESTRA_WORKSPACE/runs/<run-id>/`. The Publisher renders
  three formats from the same source:
  - `report.md` — frontmatter + Executive Summary / Findings /
    Analysis / Stress Test / Synthesis / Lucas Verdict / Citations
    / Appendix sections.
  - `report.pdf` — WeasyPrint render with a cover page, confidence
    gauge, page numbers, header + footer, and print-safe link
    styling.
  - `report.docx` — python-docx render using built-in `Heading 1`
    / `List Number` styles so Word's TOC works.
- **`/api/runs/{id}/report.md|pdf|docx`** endpoints — Markdown is
  cached from the auto-export; PDF + DOCX render lazily in a worker
  thread on first request and cache to disk. Endpoints set
  `Content-Disposition: attachment; filename=report-<run-id>.<ext>`.
- **`grok-orchestra export <run-id> --format=md|pdf|docx|all
  [--output DIR]`** — CLI command that rebuilds reports from the
  persisted `run.json` snapshot. Returns exit `0` and prints the
  written paths (or a JSON payload under `--json`).
- **`[publish]` extra** — `weasyprint`, `pydyf<0.11` (pinned for
  WeasyPrint 62 compatibility), `python-docx`, `markdown`, `pygments`.
  WeasyPrint requires Cairo + Pango on the host; the Docker image
  apt-installs them.
- **`Citation` and `ConfidenceScore` dataclasses** in
  `grok_orchestra/publisher/__init__.py` — Prompts 7 (local docs)
  and 8 (web search) will populate `Citation` directly via a future
  `run.citations` field. The publisher also harvests URLs +
  bracketed-domain refs from Harper's text as a best-effort
  fallback.
- **Frontend updates** — three download buttons (`.md` / `.pdf` /
  `.docx`) appear on the run-results panel after `run_completed`,
  plus a small SVG confidence meter beside the reasoning-token pill
  that animates as soon as Lucas reports.
- **`tests/test_publisher.py`** — 12 tests covering citation
  extraction, Markdown frontmatter / section presence, blocked-verdict
  rendering, DOCX validity (zip + `word/document.xml`), PDF
  presence (skipped when WeasyPrint isn't importable), the
  workspace path resolver, and the full
  `runner → report.md + run.json + /api/.../report.md` round-trip.
- **README "Reports" section** + system-deps install table for
  Cairo/Pango on macOS / Debian / Fedora / Windows. Comparison-
  table list grew with the report format claim.

### Added
- **Docker support.** New multi-stage `Dockerfile` (python:3.11-slim
  builder + slim runtime, venv-copy pattern so the runtime image
  carries no compilers / git), `.dockerignore` to keep the build
  context lean, `docker-compose.yml` for the one-command quickstart
  (`docker compose up --build` → http://localhost:8000), and a
  `docker-compose.dev.yml` overlay that bind-mounts `grok_orchestra/`
  on top of the venv for hot-reload development with
  `uvicorn --reload`. Image runs as a non-root `orchestra` user, ships
  a `/api/health`-based HEALTHCHECK, and is labelled with the OCI
  metadata triple (title / description / source / version / licenses).
- **GHCR publish workflow** — `.github/workflows/docker.yml` builds
  multi-arch (linux/amd64 + linux/arm64) on every push to `main` and
  every `v*.*.*` tag, then pushes to
  `ghcr.io/agentmindcloud/grok-agent-orchestra` with tags `:latest`
  (main only), `:v0.1.0` / `:0.1` (semver tags), `:main`, and
  `:sha-<short>`. Layer cache backed by GitHub Actions' `type=gha`
  backend.
- **Smoke test scripts** — `scripts/docker-smoke-test.sh` (bash) and
  `scripts/docker-smoke-test.ps1` (PowerShell). Build, boot the
  container, poll `/api/health` until 200, tear down. Safe to re-run
  and CI-friendly. Bash version exits non-zero on any failure with
  `set -euo pipefail`; PowerShell version uses
  `$ErrorActionPreference = "Stop"` and a `try/finally` cleanup.
- **`.env.example` expanded** to document every env var the stack
  knows about today (XAI_API_KEY, ORCHESTRA_MODE, LOG_LEVEL) plus
  reserved placeholders for the planned adapter providers
  (OPENAI_API_KEY, ANTHROPIC_API_KEY) and the X deploy target.
- **README "Run in Docker" section** — pre-built `docker pull` from
  ghcr.io, the compose quickstart, the dev overlay command, and a
  pointer to the smoke-test scripts. Comparison table gains a Docker
  row (✅ amd64 + arm64 on ghcr.io).

### Added
- **FastAPI web UI** at `grok-orchestra serve` (new top-level CLI
  command) with WebSocket-streamed multi-agent debates. Install the
  `[web]` extra (`fastapi`, `uvicorn[standard]`, `websockets`,
  `jinja2`, `python-multipart`). HTTP surface:
  `/`, `/api/health`, `/api/templates[?tag=]`,
  `/api/templates/{name}`, `/api/validate`, `/api/dry-run`,
  `/api/run`, `/api/runs[/{id}]`, `/ws/runs/{id}`. State is in-memory
  (last 50 runs); production should swap in Redis/SQLite. Server
  binds to `127.0.0.1` by default; no auth in v1.
- **Single-file HTML dashboard** at
  `grok_orchestra/web/templates/index.html` — Tailwind + CodeMirror
  via CDN, no JS build step. Three-pane layout: template picker /
  YAML editor + Run button / live debate stream with role-coloured
  lanes (Grok=violet, Harper=cyan, Benjamin=amber, Lucas=red). Lucas
  verdict banner + final-output copy-to-clipboard. Mobile-responsive
  (≥ 375px).
- **`event_callback` runtime hook** — `run_orchestra`,
  `run_simulated_orchestra`, `run_native_orchestra`, every pattern,
  and `run_recovery` now accept an optional callback that receives
  every stream event (`MultiAgentEvent` shape) plus synthetic
  lifecycle events (`run_started`, `debate_round_started`,
  `role_started`, `role_completed`, `lucas_started`, `lucas_passed`,
  `lucas_veto`, `pattern_started`, `pattern_phase_started`,
  `run_completed`, `run_failed`). The callback is `None` by default —
  the CLI is byte-for-byte unchanged.
- **`grok_orchestra/_events.py`** — small shared module exposing the
  `EventCallback` type, `event_dict()` factory, and
  `stream_event_to_dict()` helper. Both the CLI runtimes and the web
  layer route through these.
- **`tests/test_event_callback.py`** locks the event-shape contract;
  `tests/test_web_endpoints.py`, `tests/test_simulated_run.py`,
  `tests/test_websocket.py` exercise the full FastAPI stack via
  `TestClient` (synchronous) — every test passes regardless of
  whether `[web]` is installed (skips cleanly otherwise).
- **`templates_json_payload(...)`** in `grok_orchestra/_templates.py` —
  shared helper so the CLI's `_do_list` and the web's `/api/templates`
  cannot drift on field names.

### Changed
- The dispatcher now invokes pattern functions with `event_callback`
  via signature inspection (`inspect.signature`) rather than
  `try/except TypeError`, so a runtime `TypeError` raised during
  orchestration propagates instead of triggering a silent retry.

- **(templates session)** 8 new certified templates + retrofit
  metadata on the existing 10 (description, version, author, tags) so
  every template is filterable. Catalog ships 18 templates total. New:
  `deep-research-hierarchical`, `debate-loop-with-local-docs`
  (requires v0.3+), `competitive-analysis`,
  `due-diligence-investor-memo`, `red-team-the-plan`,
  `weekly-news-digest` (web-search full-fidelity in v0.3+),
  `paper-summarizer`, `product-launch-brief`.
- **(templates session)** `templates` sub-command group —
  `templates list` (with `--tag <tag>` and `--format {table,json}`),
  `templates show <name>`, `templates copy <name> [path]`. Bare
  `templates` defaults to `list`.
- **(templates session)** `dry-run <spec>` top-level shortcut for
  `run --dry-run`. Both `run` and `dry-run` now accept a YAML path or
  the slug of a bundled template.
- **(templates session)** Category grouping in `templates list`,
  shared with the web dashboard's left rail.
- **(templates session)** `tests/test_templates.py` — every shipped
  template parses, validates, and exposes the metadata fields.

### Fixed
- `runtime_simulated.py` and `runtime_native.py` now short-circuit
  `target: stdout` deploys with `console.print(final_content)` +
  `stdout://` sentinel — same fix that landed in `patterns.py` and
  `combined.py` last session, but those two runtimes still had the
  direct `deploy_to_target(final_content, deploy_cfg)` call which
  fails on real Bridge (`unsupported operand type(s) for /:
  'str' and 'str'`). All four call sites are now consistent.

### Fixed
- **Bridge schema strictness** — `load_orchestra_yaml` no longer
  routes Orchestra-only specs through `grok_build_bridge.parser.load_yaml`,
  whose strict `additionalProperties: false` schema rejected
  `goal:` / `orchestra:` / `safety:` / `deploy:` etc. Bridge's
  validator still runs on `combined: true` specs (which carry a real
  `build:` block).
- **`_console.section` signature mismatch** — Orchestra runtimes call
  `section(console, title)` but real Bridge ships `section(title)`.
  Installed a shim in `grok_orchestra/__init__.py` that accepts both.
- **`deploy_to_target` signature mismatch** — Bridge's
  `deploy_to_target(generated_dir, config)` is incompatible with the
  free-text final content Orchestra produces. `target: stdout` now
  short-circuits to `console.print(final_content)` and returns the
  `stdout://` sentinel instead of dispatching to Bridge.

## [0.1.0] - 2026-04-25

First public release. Grok Agent Orchestra turns a single YAML into a Grok
4.20 multi-agent run — either xAI-native (`grok-4.20-multi-agent-0309`) or a
visible prompt-simulated debate between Grok / Harper / Benjamin / Lucas —
with a real safety veto before anything ships.

### Added
- **Parser + schema**. Draft 2020-12 runtime schema at
  `grok_orchestra/schema/orchestra.schema.json` with per-pattern config
  sub-schemas. `load_orchestra_yaml()` delegates Bridge fields to
  `grok_build_bridge.parser.load_yaml`, layers the Orchestra extensions,
  applies defaults, and returns a frozen `MappingProxyType` tree.
  `OrchestraConfigError` carries a `key_path` and renders a Rich panel.
- **Enum / defaults single-source-of-truth** — `OrchestraEnums` and
  `OrchestraDefaults` frozen dataclasses in `parser.py`; schema and
  parser cannot drift.
- **OrchestraClient** — thin `XAIClient` subclass with a streaming
  `stream_multi_agent` method, yields typed `MultiAgentEvent`s, emits a
  `kind="rate_limit"` event on retry-exhausted `RateLimitError`.
- **Native runtime** — `run_native_orchestra` drives the six-phase
  native flow (resolve → stream → audit → veto → deploy → summary)
  inside a live `DebateTUI`.
- **Simulated runtime** — `run_simulated_orchestra` renders a visible
  named-role debate (Grok / Harper / Benjamin / Lucas) with rolling
  transcript compaction, per-role tool routing, and a final Grok
  synthesis turn.
- **DebateTUI** — Rich-`Live` 4-region layout (header / reasoning
  gauge / streamed text / tool-call footer), monochrome cyan/white
  rounded boxes, zero flicker. Re-entrant so the combined runtime can
  wrap phases 2-4 in one continuous show. Degrades gracefully to
  structured log lines on non-TTY stdout.
- **Lucas veto** — `safety_lucas_veto` invokes Lucas at
  `reasoning_effort="high"` on `grok-4.20-0309` with a strict JSON
  output shape; robust parser handles code-fence stripping + regex
  fallback; malformed responses retry with a terser prompt; low
  confidence downgrades to `safe=False`; `print_veto_verdict`
  renders a green approval / red denial panel.
- **Five orchestration patterns** — `hierarchical`, `dynamic-spawn`,
  `debate-loop`, `parallel-tools`, `recovery` — each a composition on
  top of the existing runtimes (<120 LOC each).
  `run_dynamic_spawn` fans out concurrent Harper+Lucas mini-debates
  via `asyncio.gather` over `asyncio.to_thread`. `run_debate_loop`
  iterates with a mid-loop Lucas veto and a structured consensus
  check that exits early.
- **Dispatcher** — `run_orchestra(config, client=None)` resolves
  pattern + mode, looks up the pattern function via `getattr` so
  `unittest.mock.patch` works, and wraps in `run_recovery` when
  `fallback_on_rate_limit.enabled`.
- **Combined Bridge + Orchestra runtime** — `run_combined_bridge_orchestra`
  drives Bridge `generate_code` → `scan_generated_code` → Orchestra
  dispatch (goal augmented with a code summary) → final Lucas veto →
  deploy → summary, all inside one continuous Live panel. `CombinedResult`
  + `BridgeResult` frozen dataclasses.
- **CLI** — `grok-orchestra` Typer app with eight commands: `run`,
  `combined`, `validate`, `templates`, `init`, `debate`, `veto`,
  `version`. Global flags `--no-color`, `--log-level`, `--json`,
  `--version`. Branded violet-accent banner renders once per
  invocation.
- **Exit-code contract** — 0 success / 2 config / 3 runtime /
  4 safety-veto / 5 rate-limit. Every error renders a red Rich panel
  with class, message, and 3-5 "What to try next" bullets.
- **Ten certified templates** + machine-readable `INDEX.yaml` catalog
  covering every pattern and both combined variants.
- **VS Code integration** — Draft-07 user-facing schema with
  `markdownDescription` + `markdownEnumDescriptions` on every field,
  10 YAML snippets, and a package.json patch binding the schema to
  `grok-orchestra.yaml` / `*.orchestra.yaml` / `*.combined.yaml`.
- **Dry-run preview path** — `DryRunOrchestraClient` and
  `DryRunSimulatedClient` replay canned streams keyed on prompt
  shape (role turn / synthesis / classification / consensus / veto)
  so every template + every pattern can be previewed without a live
  xAI call.
- **CI matrix** — lint + test (py3.10/3.11/3.12) + schema-check +
  safety-scan + build + PyPI release on tag. Coverage enforced at
  ≥85%.

### Changed
- **README rewritten as a conversion-grade landing page.** New hero
  block, honest GPT-Researcher comparison table, three-path Quickstart
  (PyPI / GitHub / editable), runnable first-orchestration walkthrough,
  60-second architecture diagram (Mermaid + ASCII fallback), highlighted
  templates, and a thematic roadmap. `docs/images/` placeholder added
  for the TUI demo GIF.

### Build & Release
- **Modernised packaging.** `pyproject.toml` migrated from setuptools to
  Hatchling (PEP 517/621). Dependencies pinned to major-version ranges
  so users do not get stuck on a point release. New `dev`, `web`, and
  `docs` extras (the latter two are placeholders for upcoming work).
- **Dedicated PyPI publish workflow.** `.github/workflows/publish.yml`
  builds wheel + sdist on every `v*.*.*` tag push and publishes via
  PyPI trusted publishing (OIDC). The `release` job has been removed
  from `ci.yml` to avoid double-publishing.
- **Smoke tests for the installed CLI.** `tests/test_cli_smoke.py`
  shells out to the `grok-orchestra` console-script entry point so we
  catch packaging-layer breakage that the in-tree unit tests cannot.
- **Releasing guide.** `docs/RELEASING.md` documents the tag-driven
  publish flow plus a manual `twine` fallback.

### Security
- Lucas veto is enabled by default (`safety.lucas_veto_enabled: true`)
  and fails closed on malformed responses. The combined runtime adds
  a second veto pass on the synthesised content before deploy. See
  [SECURITY.md](SECURITY.md) for the responsible-disclosure policy.

[Unreleased]: https://github.com/agentmindcloud/grok-agent-orchestra/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/agentmindcloud/grok-agent-orchestra/releases/tag/v0.1.0
