# Changelog — Agent Orchestra VS Code extension

## [0.1.0] — Unreleased

Initial release. Tracks the parent repo's v0.1.0 (Bridge-paired)
baseline. Marketplace publishing is intentionally disabled until a
v1.x release — the extension is build-from-source-only and ships as
a `.vsix` you sideload with `code --install-extension`.

### Added

- Five commands: **Run current YAML**, **Run a template…**,
  **Open dashboard**, **View last report**, **Compare two runs…**.
- Side-panel debate webview with role-coloured lanes
  (Harper / Benjamin / Grok) and a sticky Lucas judge bench.
- Activity-bar view container with two trees: **Templates** (live
  from the configured backend's `/api/templates`, falling back to a
  built-in list) and **Recent runs** (in-memory, this session).
- Status bar item showing transport availability — local CLI,
  remote, or offline — with a click-through to the dashboard
  command.
- Schema-aware YAML completions + diagnostics for
  `*.orchestra.yaml` / `*.orchestra.yml` via the bundled
  `schemas/orchestra.schema.json`.
- Snippets for native run, debate-loop, deep-research, lucas-veto
  block, web-search source, MCP source.
- Auto-detected transport: prefers `grok-orchestra` CLI on PATH;
  falls back to `agentOrchestra.serverUrl` (FastAPI). Bearer-token
  auth via `agentOrchestra.remoteToken`.
- Branded SVG sources (`media/icon.svg`, `media/banner.svg`) used
  for the bundled `.vsix`; regeneration steps in `media/README.md`.
- Smoke test (`test/extension.test.ts`) covering command
  registration, view-container contribution, schema contribution,
  and activation.
- CI workflow (`.github/workflows/vscode-extension.yml`) running
  lint + typecheck + esbuild bundle + `vsce package` on every PR
  so the `.vsix` build stays honest. The `vsce publish` step and
  the `vscode-v*` tag trigger are commented out — Marketplace
  publishing reactivates with a v1.x release.
