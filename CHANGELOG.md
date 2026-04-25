# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **8 new certified templates** + retrofit metadata on the existing 10
  (description, version, author, tags) so every template is filterable.
  Catalog now ships 18 templates total. New templates:
  `deep-research-hierarchical`, `debate-loop-with-local-docs`
  (requires v0.3+), `competitive-analysis`,
  `due-diligence-investor-memo`, `red-team-the-plan`,
  `weekly-news-digest` (web-search full-fidelity in v0.3+),
  `paper-summarizer`, `product-launch-brief`.
- **`templates` sub-command group** — `templates list` (with
  `--tag <tag>` filter and `--format {table,json}`),
  `templates show <name>` (prints raw YAML to stdout),
  `templates copy <name> [path]` (alias for `init`). Bare
  `templates` defaults to `list` for back-compat.
- **`dry-run <spec>`** — top-level shortcut for `run --dry-run`. Both
  `run` and `dry-run` now accept either a YAML path or the slug of a
  bundled template (e.g. `grok-orchestra dry-run red-team-the-plan`).
- **Category grouping** in `templates list` — templates are bucketed
  into Research / Business / Technical / Debate / Fast / Deep /
  Local-docs / Web-search based on their first recognised tag.
- **`tests/test_templates.py`** — every shipped template parses,
  validates, and exposes the metadata fields the catalog UI needs.
  Plus a stable-shape "snapshot" assertion on `templates list` JSON.

### Changed
- README "Templates" section now lists all 18 templates in a single
  table with pattern + tag columns and runnable CLI examples.

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
