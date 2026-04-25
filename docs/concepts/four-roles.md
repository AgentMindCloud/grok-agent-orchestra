# Four roles

Every Agent Orchestra run revolves around four named roles. They're not avatars
or personas — each role has a distinct system prompt, tool allowlist, and
position in the debate.

| Role     | Function          | Default model      | Tools (out of the box)              |
| -------- | ----------------- | ------------------ | ----------------------------------- |
| **Grok**     | coordinator   | `grok-4.20-0309`   | none — synthesises only             |
| **Harper**   | researcher    | `grok-4.20-0309`   | `web_search`, `x_search`            |
| **Benjamin** | logician      | `grok-4.20-0309`   | `code_execution`                    |
| **Lucas**    | contrarian + veto | `grok-4.20-0309` | none — operates only on the transcript |

The default models are Grok across the board because the framework's home base is
xAI's native multi-agent endpoint — but every role can be overridden per-template
via `agents[].model`. See [Multi-provider LLM](../guides/multi-provider-llm.md).

## Why named roles matter

The trick that distinguishes Orchestra from a "single agent with multiple turns"
loop is **disagreement**. Each role is *prompted to disagree with the others*,
not to align. Harper drags up evidence; Benjamin attacks the logic; Lucas hunts
for the failure mode; Grok synthesises only after the others have finished
poking.

That separation lets the safety veto live as a first-class step rather than a
post-hoc filter. Lucas's input is the *full debate*, not the synthesised draft.

## Customising the roster

The `agents:` block in YAML accepts the four canonical names plus `custom`:

```yaml
orchestra:
  agents:
    - {name: Grok,     role: coordinator,  model: grok-4.20-0309}
    - {name: Harper,   role: researcher,   model: openai/gpt-4o-mini}
    - {name: Benjamin, role: logician,     model: ollama/llama3.1:8b}
    - {name: Lucas,    role: contrarian,   model: anthropic/claude-3-5-sonnet}
```

This is the **mixed** mode: each role on a different provider. The dispatcher
tags the run with `mode_label="mixed"` and the cost panel breaks down spend by
provider.

!!! tip "Lucas should be the strict one"
    A common pattern is to put every other role on a cheap model and reserve the
    most rigorous model for Lucas. The veto step is where mistakes hurt — it's
    the right place to spend tokens.

## Tool routing

Tools are declared per-role:

```yaml
orchestra:
  tool_routing:
    Grok:     []                          # synthesis only
    Harper:   [web_search, x_search]
    Benjamin: [code_execution]
    Lucas:    []
```

When a role's tool list is empty (or absent), it operates purely from the
transcript. Lucas is intentionally tool-free by default so its judgments are
deterministic across re-runs.

For real research, see [Web search](../guides/web-search.md) — Harper's web
search is backed by Tavily (BYOK) plus an HTTP fetcher with a SHA-keyed cache,
robots.txt, and a per-run budget.

## Next

- [Lucas veto](lucas-veto.md) — the safety story.
- [Debate loop](debate-loop.md) — round-by-round flow.
- [Dynamic spawn](dynamic-spawn.md) — when 4 roles isn't enough.
