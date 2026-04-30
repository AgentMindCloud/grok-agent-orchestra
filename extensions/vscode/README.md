# Agent Orchestra — VS Code

Run multi-agent research orchestrations directly from your editor.
Four named roles (Grok, Harper, Benjamin, Lucas) argue on screen
inside a side-panel webview; Lucas's strict-JSON pass either approves
or vetoes the synthesis before it ships. The full framework lives at
[**grok-agent-orchestra**](https://github.com/agentmindcloud/grok-agent-orchestra).

> The full UI walkthrough lives on the project page — Marketplace
> publishing rejects SVG previews and the bitmap captures aren't
> branded yet. Coming back as PNG before the v1.0 listing.

## Features

- **Right-click → Run with Agent Orchestra** on any YAML file.
- **Live debate stream** in a side panel — role-coloured lanes plus
  the Lucas judge bench.
- **Schema-aware completions** for `*.orchestra.yaml` / `*.orchestra.yml`
  via the bundled JSON schema.
- **Snippets** for the common patterns: native run, debate-loop,
  deep-research planner, web-search source, MCP source, lucas-veto.
- **Activity-bar view** with a Templates tree (live from your
  configured backend) + a Recent runs tree.
- **Status bar** showing transport availability (local CLI / remote
  HTTP / offline).
- **Two transports, auto-detected**: a local `grok-orchestra` CLI on
  `$PATH` (Bridge + Orchestra installed) or a remote FastAPI at
  `agentOrchestra.serverUrl`. Local wins when both are available.

> **Marketplace publishing is intentionally disabled until a v1.x
> release.** Build from source and sideload the `.vsix` — see below.

## Install (build from source)

```bash
git clone https://github.com/agentmindcloud/grok-agent-orchestra
cd grok-agent-orchestra/extensions/vscode
npm install
npm run package
npm run vsce:package          # → agent-orchestra.vsix
code --install-extension agent-orchestra.vsix
```

## Quickstart

1. Install the extension as above.
2. Either:
   - **Local**: install Bridge then Orchestra so `grok-orchestra` is on
     your `$PATH`. The status bar shows "Orchestra · local".
   - **Remote**: run `grok-orchestra serve` (or any other deployment of
     the FastAPI) and set `agentOrchestra.serverUrl`.
3. Open any `*.orchestra.yaml` file (or use the built-in templates
   via the Activity Bar) and run `Agent Orchestra: Run current YAML`.

## Configuration

| Setting | Default | What it does |
| --- | --- | --- |
| `agentOrchestra.serverUrl` | `http://localhost:8000` | Remote FastAPI base URL. |
| `agentOrchestra.localCli.enabled` | `auto` | `auto` / `always` / `never` — controls whether the extension prefers the CLI. |
| `agentOrchestra.defaultTemplate` | `red-team-the-plan` | Pre-selected slug in the template picker. |
| `agentOrchestra.remoteToken` | _empty_ | Bearer token sent on remote calls (matches the backend's `GROK_ORCHESTRA_AUTH_PASSWORD`). |
| `agentOrchestra.workspacePath` | `${workspaceFolder}/.agent-orchestra-workspace` | Where the local CLI writes `report.md` / `run.json`. |

## Commands

- **Agent Orchestra: Run current YAML** — runs the file in the
  active editor as a spec.
- **Agent Orchestra: Run a template…** — picks a bundled template
  from the backend catalogue.
- **Agent Orchestra: View last report** — opens the latest run's
  `report.md`.
- **Agent Orchestra: Compare two runs…** — opens two reports in a
  side-by-side diff.
- **Agent Orchestra: Open dashboard** — opens the configured
  `serverUrl` in the system browser.

## Anti-patterns avoided

- **No separate auth flow.** Local-CLI mode requires zero login;
  remote mode reads a single bearer token from settings (or the
  matching env var).
- **No reimplementation of the dashboard.** This extension is
  optimised for the inner loop — for the full courtroom view (rich
  debate visualisation, citation popovers, deep-research tree),
  click `Open dashboard` to launch the Next.js frontend.
- **No bundled Tailwind / shadcn.** The webview ships ~30 KB of
  React + inline styles using VS Code theme tokens — it inherits
  your editor theme automatically.

## Development

```bash
cd extensions/vscode
npm install
npm run watch          # esbuild watch
# F5 in VS Code to launch the Extension Development Host
```

Package locally:

```bash
npm run vsce:package   # → agent-orchestra.vsix
```

## License

Apache-2.0. Built on top of
[grok-agent-orchestra](https://github.com/agentmindcloud/grok-agent-orchestra).
