# Orchestra in VS Code

Rich IntelliSense, hover docs, and snippets for Orchestra YAML — so the
schema doubles as the documentation most users ever read.

## 1. Install the prerequisites

1. Install the Red Hat **YAML** extension
   (`redhat.vscode-yaml`) — this is what resolves JSON schemas for YAML
   files.
2. Install (or update) the Grok Install Ecosystem VS Code extension so
   it ships the Orchestra schema + snippets. If you're bootstrapping a
   fresh extension fork, merge `vscode/package.json.patch` into your
   extension's `package.json` and copy `vscode/schemas/` +
   `vscode/snippets/` alongside it.

## 2. File-name conventions

The patch binds the schema by filename:

| Pattern              | Purpose                                        |
|----------------------|------------------------------------------------|
| `grok-orchestra.yaml`  | Conventional project-root spec                 |
| `*.orchestra.yaml`     | Per-flow specs, e.g. `trendseeker.orchestra.yaml` |
| `*.combined.yaml`      | Combined Bridge + Orchestra specs              |

Use any of these names and VS Code auto-attaches the schema — no
per-file `# yaml-language-server: $schema=…` comment required.

## 3. First file

```yaml
# trendseeker.orchestra.yaml
name: trendseeker
goal: "Draft a tweet about today's xAI launch."

orchestra:
  mode: | # ← cursor here → Ctrl-Space → autocompletes native | simulated | auto
    auto

safety:
  lucas_veto_enabled: true

deploy:
  target: stdout
  post_to_x: false
```

With the cursor on `mode:` and an empty value:

- **Ctrl-Space** suggests `native` / `simulated` / `auto`.
- **Hover** on each suggestion shows the full "when to use / cost
  impact / visibility" block from the schema.

The same works for:

- `orchestra.orchestration.pattern` — every pattern has a detailed
  when-to-use doc and a cost estimate.
- `orchestra.agents[].name` — each canonical role shows its system
  prompt responsibilities (Grok / Harper / Benjamin / Lucas).
- `orchestra.reasoning_effort` — shows how each level maps to
  `agent_count` and the relative token cost.
- `safety.lucas_veto_enabled` — hovers surface the strong
  recommendation to keep this `true`.
- `orchestra.tool_routing.<agent>` — each tool enum has a short
  description.

## 4. Snippets

Ten starter snippets ship alongside the schema. In any YAML file with a
matching filename, type the prefix and press **Tab**:

| Prefix               | What it drops in                                          |
|----------------------|-----------------------------------------------------------|
| `orch-min`             | Minimal valid Orchestra spec                              |
| `orch-native-4`        | Native 4-agent spec (baseline cost)                       |
| `orch-native-16`       | Native 16-agent spec (~4× cost, higher quality)           |
| `orch-simulated`       | Visible 4-role debate (Grok / Harper / Benjamin / Lucas)  |
| `orch-hierarchical`    | ResearchTeam → CritiqueTeam → synthesis                   |
| `orch-dynamic-spawn`   | Decompose into N sub-tasks, fan out concurrent mini-debates |
| `orch-debate-loop`     | Iterative pattern with mid-loop Lucas veto + consensus    |
| `orch-parallel-tools`  | Native with explicit per-agent tool routing               |
| `orch-recovery`        | Recovery wrap around a pattern                            |
| `orch-combined`        | Combined Bridge + Orchestra run                           |

Snippets use tab-stops for the fields you are most likely to change
(name, goal, counts) so you can fill them in without leaving the
keyboard.

## 5. Troubleshooting

- **No completions on `mode:`** — confirm the Red Hat YAML extension is
  active and that the file name matches one of the patterns in section
  2. Reload the window (`Cmd/Ctrl-Shift-P → Developer: Reload Window`).
- **Schema mismatch warning** — the bundled schema mirrors
  `grok_orchestra/schema/orchestra.schema.json`. If you upgraded the
  `grok-agent-orchestra` package but not the VS Code extension, the
  two may briefly disagree — update the extension to get the matching
  schema.
- **Want the schema elsewhere?** — point your YAML config at the
  schema file directly:

  ```yaml
  # yaml-language-server: $schema=./path/to/orchestra.schema.json
  ```

## 6. Related

- Orchestra CLI: `grok-orchestra --help`, `grok-orchestra templates`,
  `grok-orchestra init <template>` to scaffold a spec on disk.
- Project docs: [orchestra.md](./orchestra.md).
- Schema source: `grok_orchestra/schema/orchestra.schema.json` (runtime)
  and `vscode/schemas/orchestra.schema.json` (user-facing IntelliSense).
