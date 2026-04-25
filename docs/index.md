---
title: Agent Orchestra
hide:
  - navigation
  - toc
---

# Agent Orchestra

**Multi-agent research with visible debate and enforceable safety vetoes — powered by Grok.**

> Multi-agent research that runs free on your laptop OR scales up with your favorite cloud LLM.

Four named roles — **Grok** (executive), **Harper** (research), **Benjamin** (logic),
**Lucas** (veto) — argue on screen and ship a citation-rich report. Lucas's strict-JSON
veto is the framework's safety gate; nothing leaves the box without it.

<div class="orchestra-cards" markdown>

<a class="orchestra-card" href="getting-started/quickstart/" markdown>
### ▸ Quickstart
Get a real run on your laptop in 60 seconds — no API keys required.
</a>

<a class="orchestra-card" href="architecture/overview/" markdown>
### ▸ Architecture
The 60-second tour: roles, debate loop, veto, publisher, tracing.
</a>

<a class="orchestra-card" href="guides/templates/" markdown>
### ▸ Templates
18 certified templates covering research, debate, business, and code-review patterns.
</a>

</div>

## Why Agent Orchestra

- **Visible debate, not a black box.** Every role turn, tool call, and reasoning
  gauge streams into the TUI / dashboard while it happens.
- **Lucas veto = enforceable safety gate.** A separate `grok-4.20-0309` pass with
  strict-JSON output, high reasoning effort, and *fail-closed* defaults. Malformed,
  low-confidence, or timed-out → exit code 4 → nothing ships.
- **Bring your own model.** Grok native is the power mode; OpenAI / Anthropic /
  Ollama / Mistral / Bedrock / Azure all plug in via the LiteLLM adapter from
  the same YAML. Mix-and-match per-role for a cheaper Harper + a strict Lucas.
- **Reports built in.** Every run auto-writes Markdown + run.json. PDF (WeasyPrint)
  and DOCX (python-docx) render lazily on first download, with optional inline
  Flux-generated illustrations.
- **Observability is opt-in.** LangSmith / Langfuse / OTLP backends behind a single
  `Tracer` Protocol. NoOpTracer is the default and adds zero overhead.

## Three tiers

Pick the one that matches your machine right now. `grok-orchestra doctor` reports
which tiers are configured.

| Tier | Setup | Cost | Best for |
| --- | --- | --- | --- |
| **Demo** | `pip install grok-agent-orchestra` | $0 | First five minutes; the README hero GIF |
| **Local** | `+ ollama pull llama3.1:8b` and the `[adapters]` extra | $0 | Privacy-sensitive runs; offline laptops |
| **Cloud** | `+ XAI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Pay-as-you-go | Production, customer-facing reports |

## Bring your own key (BYOK)

Every credential is read from the environment via the provider SDK's own
resolver. The framework never embeds, ships, transmits, or logs raw values.
The PII scrubber redacts known token shapes from every traced span before
transit. See [Tracing](guides/tracing.md) and the
[Comparison vs GPT-Researcher](architecture/comparison.md) for details.

## Stay in touch

- [GitHub](https://github.com/agentmindcloud/grok-agent-orchestra)  ·  give it a
  star to follow releases.
- [PyPI](https://pypi.org/project/grok-agent-orchestra/)  ·  `pip install
  grok-agent-orchestra`.
- Discord — _coming soon_; the invite will land here when it does.
