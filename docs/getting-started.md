# Getting started

From `git clone` to a green Lucas approval in about five minutes.
Every step lists the exact command to run and the output you should
see — if something different appears, jump to
[Troubleshooting](#troubleshooting) at the bottom.

- [Before you start](#before-you-start)
- [Step 1 — get an xAI API key](#step-1--get-an-xai-api-key)
- [Step 2 — install from source](#step-2--install-from-source)
- [Step 3 — first dry-run](#step-3--first-dry-run)
- [Step 4 — first real run](#step-4--first-real-run)
- [Step 5 — pick a template for your use case](#step-5--pick-a-template-for-your-use-case)
- [Step 6 — tweak the spec](#step-6--tweak-the-spec)
- [Troubleshooting](#troubleshooting)

## Before you start

You need:

- **Python 3.10+** — check with `python --version`.
- **git** — to clone Orchestra and its companion, Grok Build Bridge.
- **About 5 minutes** of attention and **no token budget** — everything
  in this guide runs in `--dry-run` mode until Step 4.

## Step 1 — get an xAI API key

Only needed for Step 4 onward. If you only want to see the TUI via
`--dry-run`, skip to Step 2.

1. Go to <https://console.x.ai/> and sign in with your X account.
2. Open **API keys** and create a new key. Copy it — it starts with
   `sk-xai-…`.
3. Put it in your shell:

   ```bash
   export XAI_API_KEY="<paste-your-key-here>"   # starts with sk-xai-
   ```

   To make it stick across terminals, add the line to your
   `~/.bashrc` / `~/.zshrc` / `~/.config/fish/config.fish`.

   **Bring your own key.** This project never embeds, ships, or
   transmits keys — the framework only reads `XAI_API_KEY` from your
   shell or a local `.env` (which `.gitignore` keeps out of every
   commit). Lose the key → rotate it on the xAI console; nothing
   else needs to change.

## Step 2 — install from source

Orchestra depends on its sibling project **Grok Build Bridge**, which
ships the shared `XAIClient`, parser, safety scan, and deploy
primitives. Until Bridge hits PyPI, install both from source in
order:

```bash
# Pick a workspace directory.
mkdir -p ~/grok && cd ~/grok

# 1. Clone + install Bridge.
git clone https://github.com/agentmindcloud/grok-build-bridge.git
pip install -e ./grok-build-bridge

# 2. Clone + install Orchestra.
git clone https://github.com/agentmindcloud/grok-agent-orchestra.git
pip install -e ./grok-agent-orchestra
```

Confirm the CLI installed cleanly:

```bash
grok-orchestra --version
```

Expected output:

```
grok-orchestra 0.1.0
```

Then see the branded banner + full command list:

```bash
grok-orchestra --help
```

You should see a rounded panel with an ASCII "Grok Orchestra" title
in a cyan-to-violet gradient, the tagline **4 minds. 1 safer post.
Zero compromise.**, and a list of eight commands: `version`,
`validate`, `templates`, `init`, `run`, `combined`, `debate`, `veto`.

## Step 3 — first dry-run

`--dry-run` replays a canned stream so you can see the TUI and
exit-code contract without burning any tokens. Do this **once**
before ever running a real spec — it confirms the install works.

```bash
cd ~/grok/grok-agent-orchestra

grok-orchestra run examples/simulated-hello.yaml --dry-run
```

What you should see (~2 seconds of streaming output):

1. The branded banner.
2. A section header **🎯  Resolve roles** followed by a dim log line
   listing the four roles (`Grok`, `Harper`, `Benjamin`, `Lucas`).
3. A section header **🎤  Debate** and a live Rich panel showing:
   - a reasoning-token gauge on the left,
   - streaming tokens on the right with coloured role dividers,
   - a tool-calls footer.
4. A section header **🛡️  Lucas veto** and a **green** panel titled
   **Lucas — safety verdict** with **✅  Lucas approves** and a
   confidence near 0.91.
5. A section header **🚀  Deploy** showing a canned `deploy_to_target
   → https://example.test/deployed`.
6. A final green panel **grok-orchestra · run** with `mode=simulated`,
   `duration: …`, `events: …`, and the synthesised final text.

Exit code should be `0`.

Try another template:

```bash
grok-orchestra run examples/native-hello.yaml --dry-run
```

Same shape, `mode=native` in the summary.

### See a veto in action

Run the deliberately-toxic fixture so you know what a **denial**
looks like:

```bash
grok-orchestra run examples/simulated-toxic.yaml --dry-run
```

You should see:

- The usual debate TUI.
- A **red** panel titled **Lucas — safety verdict** with **⛔  Lucas
  vetoes**, two `reasons`, and a yellow-bordered sub-panel
  **Lucas's suggested rewrite**.
- Deploy is **skipped**.
- A red **✗ run complete** summary.
- Exit code **4** (safety veto).

This is the exit-code contract: `0` success, `2` bad config, `3`
runtime error, `4` safety veto, `5` rate limit.

## Step 4 — first real run

Once the dry-run works and you've exported `XAI_API_KEY`, drop the
flag:

```bash
grok-orchestra run examples/simulated-hello.yaml
```

The run is slower now — every role turn is a real xAI call. Expect
**~30-60 seconds** for a 2-round simulated run, **~15-30 seconds**
for a native-4 run.

If the run succeeds, the deploy step prints `stdout://<sha>` and the
final summary panel shows the synthesised post. Nothing actually
posts to X — the example's `deploy.target` is `stdout`.

When you're ready to post for real, change `deploy` in your spec to:

```yaml
deploy:
  target: x
  post_to_x: true
```

…and make sure the necessary X API credentials are configured (a
Bridge-side release gate — track the status in Bridge's README).

## Step 5 — pick a template for your use case

List every shipped template, with pattern badges:

```bash
grok-orchestra templates
```

Or get machine-readable JSON:

```bash
grok-orchestra --json templates
```

### A 3-question picker

Answer top-to-bottom; the first **yes** picks your template.

| Question                                                           | Template                                      |
|--------------------------------------------------------------------|-----------------------------------------------|
| Do you want Bridge to **generate code first** and then debate it?  | `combined-trendseeker` or `combined-coder-critic` |
| Is your goal **contested / needs balance** and you can spare 5 iterations? | `orchestra-debate-loop-policy`                |
| Do you want a **visible 4-role debate** over a specific fact-check?        | `orchestra-simulated-truthseeker`             |
| Does your goal split naturally into **N parallel sub-analyses**?           | `orchestra-dynamic-spawn-trend-analyzer`      |
| Do you want a **two-team research-then-critique** workflow?               | `orchestra-hierarchical-research`             |
| Do you need **strict per-agent tool permissions**?                         | `orchestra-parallel-tools-fact-check`         |
| Is this a **scheduled / production** run where rate limits bite?           | `orchestra-recovery-resilient`                |
| Is this a **deep-research weekly thread** (long-form, 5-8 tweets)?         | `orchestra-native-16`                         |
| Otherwise — baseline daily X thread                                         | `orchestra-native-4`                          |

### Scaffold your chosen template to disk

```bash
grok-orchestra init orchestra-native-4 --out my-spec.yaml
```

Expected output: a green **✓ template written** panel with a
`source → dest` line and two suggested next steps.

## Step 6 — tweak the spec

Open `my-spec.yaml` in your editor. Change these three lines first:

1. **`goal:`** — the actual instruction. Be specific: constraints,
   tone, format. The bundled templates show what a strong goal looks
   like.
2. **`safety.confidence_threshold:`** — raise to `0.85` for anything
   that ships to X; keep `0.75` (default) for drafts.
3. **`deploy.target:`** — stays `stdout` until you're ready to post
   for real.

If you have VS Code:

```bash
code my-spec.yaml
```

Install the Red Hat YAML extension + the Grok extension (see
[`docs/vscode-orchestra.md`](vscode-orchestra.md)). The file name
`my-spec.yaml` does not trigger the schema by default — rename to
`my-spec.orchestra.yaml` and you get full IntelliSense on every
field.

Validate before you run:

```bash
grok-orchestra validate my-spec.orchestra.yaml
```

Expected output: a violet-bordered panel with **✓ spec is valid**,
the resolved `mode`, `pattern`, and `combined` flag.

Preview the debate (no tokens):

```bash
grok-orchestra run my-spec.orchestra.yaml --dry-run
```

Ship it (real tokens):

```bash
grok-orchestra run my-spec.orchestra.yaml
```

Nice. You just drove a Grok 4.20 multi-agent run from a YAML.

## Troubleshooting

### `ModuleNotFoundError: No module named 'grok_build_bridge'`

You skipped Step 2's Bridge install. Fix:

```bash
pip install -e ./grok-build-bridge
```

### `ModuleNotFoundError: No module named 'xai_sdk'`

Dependencies didn't install for some reason. Fix:

```bash
pip install xai-sdk
```

### `Orchestra config error — Additional properties are not allowed`

The spec uses a key the schema doesn't recognise. The panel points at
the exact key path (`at: orchestra.orchestration.config`). Check
[`docs/orchestra.md`](orchestra.md#yaml-reference) for the allowed
shape for that pattern's `config` block, or run:

```bash
grok-orchestra validate my-spec.orchestra.yaml
```

### `XAIError: API key not set`

`XAI_API_KEY` is not exported in the current shell. Either export it
(Step 1) or re-run the command with `--dry-run` to verify without a
key.

### Exit code **4** — Lucas vetoed

Read the red verdict panel:

1. The **reasons** list tells you what Lucas flagged.
2. If Lucas attached an **alternative_post** and your spec has
   `safety.max_veto_retries >= 1`, the runtime already retried once
   with the rewrite. If you see **two** red panels, both passes
   failed.
3. Edit the `goal` to address the flagged concerns, or raise
   `safety.confidence_threshold` if you think Lucas was too harsh.

### Exit code **5** — rate limit after recovery

xAI capped you. Try one:

- Lower `orchestra.reasoning_effort` from `high` → `medium`.
- Drop `orchestra.agent_count` from `16` → `4`.
- Enable auto-degrade:

  ```yaml
  orchestra:
    orchestration:
      fallback_on_rate_limit:
        enabled: true
        fallback_model: grok-4.20-0309
        lowered_effort: medium
  ```

- Wait a minute and retry — xAI rate-limit windows are short.

### Combined runtime — `Bridge safety scan flagged generated code as unsafe`

Bridge's `scan_generated_code` matched a dangerous pattern in the
generated files (`os.system`, `eval`, hard-coded secrets, …). Two
fixes:

1. **Preferred** — edit the `build:` block so the generated code
   avoids the pattern. The scan message names the file and the
   label.
2. **Override** — re-run with `--force` if you've manually reviewed
   the generated code and are confident:

   ```bash
   grok-orchestra combined my-spec.orchestra.yaml --force
   ```

### Something weirder

Re-run with debug logging:

```bash
grok-orchestra --log-level DEBUG run my-spec.orchestra.yaml --dry-run
```

Open an issue at
<https://github.com/agentmindcloud/grok-agent-orchestra/issues>
with the full traceback. Include your spec (redacted if needed) and
the `grok-orchestra --version` output.
