# Your first orchestration

Anatomy of one YAML, one CLI invocation, and one run summary.

## The YAML

The smallest spec that's *actually useful*:

```yaml
name: hello-three-languages
goal: |
  Draft a 3-tweet X thread on today's most-discussed topic in AI agent
  orchestration. Hook + headline, one piece of evidence, one takeaway.

orchestra:
  mode: simulated                      # `native` for the multi-agent endpoint
  agent_count: 4
  reasoning_effort: medium
  debate_rounds: 1
  orchestration:
    pattern: native                    # see Concepts → Debate loop
  agents:
    - {name: Grok,     role: coordinator}
    - {name: Harper,   role: researcher}
    - {name: Benjamin, role: logician}
    - {name: Lucas,    role: contrarian}

safety:
  lucas_veto_enabled: true
  confidence_threshold: 0.80           # Lucas's strict-JSON gate
  max_veto_retries: 1

deploy:
  target: stdout
```

Every field has a default — see [Reference → YAML schema](../reference/yaml-schema.md)
for the full surface.

## Running it

=== "From a template"

    ```bash
    grok-orchestra init hello-three-languages --out my.yaml
    grok-orchestra run my.yaml --dry-run     # no API key needed
    grok-orchestra run my.yaml               # live (needs XAI_API_KEY)
    ```

=== "Via the dashboard"

    ```bash
    grok-orchestra serve
    # → pick a template, toggle Simulated, click Run
    ```

## Reading the summary

A successful run prints a one-line summary on stdout and a Rich panel for each
phase. The fields that matter most:

- **Mode label** — `native` / `simulated` / `adapter` / `mixed`. See
  [Multi-provider LLM](../guides/multi-provider-llm.md).
- **Lucas verdict** — green ✅ approved or red ⛔ blocked, with the strict-JSON
  confidence + reasons.
- **Provider costs** — per-provider USD breakdown (cloud runs only).
- **Trace URL** — only populated when a [tracing backend](../guides/tracing.md)
  is configured. Deep-links to LangSmith / Langfuse / your collector.

## Where the artefacts land

When you run via the dashboard (or via the CLI with `serve` running):

```
$GROK_ORCHESTRA_WORKSPACE/runs/<run-id>/
    report.md           ← canonical markdown with frontmatter
    run.json            ← full snapshot for `grok-orchestra export`
    images/             ← if publisher.images.enabled
        cover.png
        findings.png
```

PDF + DOCX render lazily on first download via the dashboard's
**⬇ .pdf / ⬇ .docx** buttons or `grok-orchestra export <run-id> --format=all`.

## Next

- [Templates guide](../guides/templates.md) — pick from the 18 bundled starters.
- [Reports & export](../guides/reports-and-export.md) — turn a run into a PDF you'd
  share with a stakeholder.
- [Architecture overview](../architecture/overview.md) — how the pieces fit together.
