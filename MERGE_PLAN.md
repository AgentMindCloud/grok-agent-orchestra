# Merge Plan — grok-agent-orchestra

This repository will be merged into **grok-runtime** during Tier 3 (as
`runtime/dashboard/` and `runtime/server/`). After the merge, this repo will be
archived with a redirect README pointing to grok-runtime.

## Why merge

`grok-agent-orchestra` is the operator-facing surface (CLI, dashboard, multi-
agent debate). It already depends on `grok-build-bridge` for its safety
primitives and XAI client. Once `grok-runtime` lands as the unified runtime
target, keeping orchestra as a separate repo creates a duplicate release
cycle, a duplicate test matrix, and a needless versioning seam between the
runtime and the surface that exercises it.

## Layout after merge

| Today (this repo)                         | After merge (in `grok-runtime`)        |
| ----------------------------------------- | -------------------------------------- |
| `grok_orchestra/`                         | `runtime/server/orchestra/`            |
| `frontend/` (Next.js dashboard)           | `runtime/dashboard/`                   |
| `benchmarks/`                             | `runtime/benchmarks/`                  |
| `extensions/vscode/`                      | `runtime/extensions/vscode/`           |
| `skills/agent-orchestra/`                 | `runtime/skills/agent-orchestra/`      |
| `tools/bridge-stub/`                      | (deleted — Bridge is a sibling module) |
| `docs/`                                   | `runtime/docs/orchestra/`              |
| `examples/`                               | `runtime/examples/orchestra/`          |
| `tests/`                                  | `runtime/tests/orchestra/`             |

## Pre-merge checklist (must be green in this repo)

- [x] All fictional model IDs replaced with real xAI IDs (`grok-4-0709`,
      `grok-4`, `grok-2-latest`, …).
- [x] At least one deterministic benchmark lands real numbers in
      `benchmarks/results/latest.md` without external API keys
      (see `benchmarks/template_coverage.py`).
- [ ] `grok-build-bridge` v0.1.0 published — `tools/bridge-stub/` is then
      deleted and CI installs the real wheel.
- [ ] `grok-runtime` v0.1.0 has a stable public API for hosting orchestra
      runs (the runtime exposes a `RunSession` interface that orchestra
      drives).
- [ ] All orchestra dashboards render against a live `grok-runtime` server
      in a staging deploy (no fixtures).

## Merge mechanics

1. Create `runtime/server/orchestra/` and `runtime/dashboard/` directories
   in `grok-runtime` via `git subtree add` so the full history is preserved.
2. Rewrite imports: `grok_orchestra.*` → `grok_runtime.orchestra.*`.
3. Collapse the two `pyproject.toml` files: orchestra's optional extras
   (`[orchestra]`, `[orchestra-frontend]`) become extras on the runtime
   package.
4. Move CI workflows: orchestra's `benchmarks.yml` and `docs.yml` jobs
   merge into the runtime's matrix; the docker workflow is dropped (the
   runtime ships its own image).
5. Replace `tools/bridge-stub/` imports with the real `grok-build-bridge`
   PyPI package — orchestra was already designed to depend on Bridge,
   so no API surface changes.
6. Archive this repo with a `README.md` that points users at
   `grok-runtime/runtime/server/orchestra/`.

## Risk / blast radius

- **Public users**: anyone pip-installing `grok-agent-orchestra` keeps
  working — we publish one final `0.x.y` release that re-exports from the
  runtime package, then archive.
- **VS Code extension**: keeps shipping from its own marketplace listing;
  only the schema URL changes.
- **Skills package**: keeps shipping from its own Anthropic Skills entry;
  only the import target changes.

## Out of scope for the merge

- We do **not** rewrite the dashboard during the merge — it moves as-is.
- We do **not** consolidate the four-roles (`Grok` / `Harper` / `Benjamin`
  / `Lucas`) into the runtime's generic role abstraction. That happens in
  Tier 4, behind a feature flag, with its own RFC.
