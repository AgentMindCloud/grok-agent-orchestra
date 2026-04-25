# Quickstart

Five minutes to a real run with no API keys.

## 1. Install

```bash
pip install grok-agent-orchestra
```

## 2. Confirm tier readiness

```bash
grok-orchestra doctor
```

The expected output for a fresh install:

```text
✅  Demo mode ready  ·  always available — no setup required
⚠️  Local mode unavailable  ·  no Ollama at http://127.0.0.1:11434
⚠️  No cloud keys detected  ·  set XAI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY
```

This is fine. **Demo mode** is enough for the next step.

## 3. Dry-run a bundled template

The `red-team-the-plan` template is the canonical first run — it's fast, deterministic,
and exercises the full debate + Lucas veto pipeline without leaving the box.

```bash
grok-orchestra dry-run red-team-the-plan
```

You'll see all four roles take turns in a Rich TUI, Lucas approve the synthesis,
and a final report sketch print to stdout. Total runtime: ~1 second.

## 4. Open the dashboard

```bash
pip install 'grok-agent-orchestra[web]'
grok-orchestra serve
# → http://127.0.0.1:8000
```

Pick a template from the left rail, leave **Simulated** on, click **Run**. The
debate streams live with role-coloured lanes (Grok=violet, Harper=cyan,
Benjamin=amber, Lucas=red) and a confidence meter renders the moment Lucas
ships a verdict.

## 5. Up the realism

When you're ready for a real run, pick a tier:

=== "Local mode (free, Ollama)"

    ```bash
    ollama pull llama3.1:8b
    pip install 'grok-agent-orchestra[adapters]'
    grok-orchestra run examples/local-only/local-research.yaml
    ```

=== "Cloud mode (BYOK)"

    ```bash
    export XAI_API_KEY="<paste-yours-here>"           # or OPENAI_API_KEY
    grok-orchestra run weekly-news-digest             # adds web research
    ```

## What you just ran

The "debate + veto" loop is the core abstraction. The next pages walk through
each piece:

- [Your first orchestration](first-orchestration.md) — anatomy of the YAML and the run summary.
- [Concepts → Four roles](../concepts/four-roles.md) — how Grok / Harper / Benjamin / Lucas divide the work.
- [Concepts → Lucas veto](../concepts/lucas-veto.md) — why fail-closed is the safety story.
