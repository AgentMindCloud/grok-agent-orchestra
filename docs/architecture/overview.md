# Architecture overview

Agent Orchestra is one runtime with three layers: a YAML
**parser/dispatcher**, a swappable **provider** stack (LLM / Source /
Image / Tracer), and a **publisher** that renders the final report.

```mermaid
flowchart TB
  Y([YAML spec]) --> P[Parser + Schema validation]
  P --> D[Dispatcher · resolve_client]
  D --> R{Pattern}

  R -->|native|     N[Grok native multi-agent endpoint]
  R -->|simulated|  S[Multi-call orchestration over LiteLLM]
  R -->|debate-loop| L[Iterative debate · mid-loop veto · consensus]
  R -->|dynamic-spawn| F[Fan-out · concurrent sub-tasks · merge]
  R -->|hierarchical|  H[Two-team hierarchy]

  N --> RT[Runtime · emits MultiAgentEvent stream]
  S --> RT
  L --> RT
  F --> RT
  H --> RT

  RT --> SRC[(Source layer · web_search / local_docs / mcp)]
  RT --> LLM[(LLM layer · Grok / OpenAI / Anthropic / Ollama / …)]
  RT --> TR[(Tracer · LangSmith / Langfuse / OTLP / NoOp)]

  RT --> V[Lucas veto · strict-JSON · fail-closed]
  V -->|safe=true| PUB[Publisher · MD + PDF + DOCX + images]
  V -->|safe=false| BLK([exit 4 · blocked])
  PUB --> O([report.md + report.pdf + report.docx + run.json])
```

## The four roles

Every run involves the same four named agents. The framework enforces
the names so the debate transcript stays readable across providers and
across templates.

- **Grok** — executive coordinator + final synthesis.
- **Harper** — research, web + local docs.
- **Benjamin** — logic, math, code execution.
- **Lucas** — contrarian + safety veto (strict-JSON, fail-closed).

See [Four roles](../concepts/four-roles.md) for the full breakdown.

## Three tiers, one YAML

The same spec runs in three modes:

| Tier | Resolved by | Cost |
| --- | --- | --- |
| **Demo** | `mode: simulated` + dry-run client | $0 |
| **Local** | `provider: ollama` on every role | $0 |
| **Cloud** | `provider: xai / openai / anthropic / ...` | Pay-as-you-go |

`grok-orchestra doctor` reports which tiers are configured.

## What the runtime guarantees

- **Visible debate** — every role turn, tool call, reasoning gauge
  streams as a `MultiAgentEvent` with the same shape across runtimes.
- **Lucas veto is fail-closed** — malformed JSON, low confidence, or
  timeout → exit 4. Nothing slips by silent.
- **Reports always ship** — provider failures (image, tracing) are
  caught and logged; the final Markdown is the contract.
- **PII never traced** — known token shapes (Bearer, sk-…, AKIA…) are
  scrubbed from spans before transit.

## See also

- [Extending](extending.md) — add a role, source, provider, or tracer.
- [Comparison](comparison.md) — vs GPT-Researcher and friends.
- [Concepts → Lucas veto](../concepts/lucas-veto.md) — the safety gate.
