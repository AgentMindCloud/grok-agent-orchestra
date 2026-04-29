# VS Code extension

A first-party VS Code extension lives at
[`extensions/vscode/`](https://github.com/agentmindcloud/grok-agent-orchestra/tree/main/extensions/vscode).
It runs Agent Orchestra orchestrations directly from your editor, with
a side-panel webview that renders the multi-agent debate live and a
Lucas judge bench that mirrors the Next.js courtroom view.

## What you get

- **Right-click → Run with Agent Orchestra** on any YAML.
- **Live debate webview** — three role lanes (Harper / Benjamin /
  Grok) plus the Lucas judge bench. Minimal-but-faithful version of
  the Next.js courtroom (Prompt 16b).
- **Schema-aware YAML** for `*.orchestra.yaml` / `*.orchestra.yml` via
  the bundled `schemas/orchestra.schema.json`.
- **Activity-bar view** with a Templates tree (live from the configured
  backend) and a Recent runs tree.
- **Status bar** — transport availability + last-run outcome.
- **Snippets** for the canonical patterns: native run, debate-loop,
  deep-research planner, web-search / MCP sources, lucas-veto block.

## Install

**Marketplace publishing is intentionally disabled until a v1.x
release.** The extension is build-from-source only — the artefact is
a `.vsix` file you sideload with `code --install-extension`.

```bash
git clone https://github.com/agentmindcloud/grok-agent-orchestra
cd grok-agent-orchestra/extensions/vscode
npm install
npm run package
npm run vsce:package        # → agent-orchestra.vsix
code --install-extension agent-orchestra.vsix
```

The CI workflow at `.github/workflows/vscode-extension.yml` lints,
type-checks, bundles, and packages the `.vsix` on every PR so the
build step stays honest. The publish step is commented out until a
Marketplace listing is ready.

## Two transports — auto-detected

The extension shares the wire contract with the [Claude
Skill](claude-skill.md), which means it routes calls the same way:

| Mode | What it spawns | Activate by |
| --- | --- | --- |
| **Local CLI** *(preferred)* | `grok-orchestra run <slug> --json` via `child_process.spawn` | `pip install grok-agent-orchestra` |
| **Remote HTTP** | `POST /api/run` + poll `GET /api/runs/{id}` + fetch `report.md` | set `agentOrchestra.serverUrl` to a reachable FastAPI |

Force one or the other via `agentOrchestra.localCli.enabled`
(`auto` / `always` / `never`).

## Settings

Open the VS Code Settings UI and search for `agentOrchestra`. The
five contributed settings are:

- `agentOrchestra.serverUrl` — Remote FastAPI base URL. Default
  `http://localhost:8000`.
- `agentOrchestra.localCli.enabled` — `auto` / `always` / `never`.
- `agentOrchestra.defaultTemplate` — Pre-selected slug for the
  template picker. Default `red-team-the-plan`.
- `agentOrchestra.remoteToken` — Bearer token for the remote
  backend. Matches the backend's `GROK_ORCHESTRA_AUTH_PASSWORD`.
- `agentOrchestra.workspacePath` — Where the local CLI writes
  `report.md` / `run.json`. Default
  `${workspaceFolder}/.agent-orchestra-workspace`.

## Commands

| Command | What it does |
| --- | --- |
| **Run current YAML** | Spec is the file in the active editor. |
| **Run a template…** | Quick-pick over the backend's `/api/templates` list. |
| **Open dashboard** | Opens `serverUrl` in the system browser. |
| **View last report** | Opens the latest run's `report.md` (or remote URL). |
| **Compare two runs…** | Pick two recent runs → `vscode.diff` viewer. |

## Authentication

When the FastAPI backend has `GROK_ORCHESTRA_AUTH_PASSWORD` set
(the optional shared-password gate from Prompt 16d), set
`agentOrchestra.remoteToken` to the same value. The extension
sends it as `Authorization: Bearer <token>` on every request.

If you forget, the extension surfaces a 401 toast pointing at the
setting.

## Marketplace publishing

The extension is published to the VS Code Marketplace via
`.github/workflows/vscode-extension.yml` on `vscode-v*` tags.
Setup is one-time:

1. Create a Personal Access Token at
   <https://dev.azure.com/{org}/_usersSettings/tokens> with the
   `Marketplace → Manage` scope.
2. In the GitHub repo settings, add the secret as `VSCE_PAT`.
3. Tag a release: `git tag vscode-v0.1.0 && git push origin vscode-v0.1.0`.

The CI run lints, type-checks, bundles via esbuild, packages a
`.vsix`, then publishes via `vsce publish`. PRs run everything
except the publish step.

## Hand-off

The remote-HTTP code path inside `extensions/vscode/src/client/remoteClient.ts`
mirrors the Claude Skill's `remote_run.py`. When Prompt 19 lands the
benchmark harness, the same wire contract drives both surfaces — both
expect the canonical `RESULT_JSON` shape (`mode` / `runId` / `reportPath` /
`reportUrl` / `vetoReport` / `exitCode`).

## See also

- [Claude Skill](claude-skill.md) — sister integration; shares the
  remote HTTP contract.
- [Architecture overview](../architecture/overview.md)
- [CLI reference](../reference/cli.md)
- [YAML schema](../reference/yaml-schema.md)
