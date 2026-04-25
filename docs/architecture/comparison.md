# Comparison vs GPT-Researcher

The closest open-source comparable to Agent Orchestra is
[gpt-researcher](https://github.com/assafelovic/gpt-researcher). Both
do multi-agent research and ship a report. This page is a feature-by-
feature line-up so you can pick the right tool.

## At a glance

| Feature | Agent Orchestra | GPT-Researcher |
| --- | --- | --- |
| **Visible debate** | ✅ Four named roles, streaming TUI + dashboard | 🟡 Single agent + sub-tasks |
| **Safety veto** | ✅ Lucas, strict-JSON, fail-closed | ❌ |
| **Native multi-agent endpoint** | ✅ Grok native | ❌ |
| **Multi-provider LLM** | ✅ LiteLLM (xAI / OpenAI / Anthropic / Ollama / …) | ✅ OpenAI / Anthropic / Ollama |
| **Local docs** | ✅ PDF + Markdown + TXT, BM25, no upload | ✅ PDF |
| **Web search** | ✅ Tavily (cache + robots.txt) | ✅ Tavily / Bing / Serper |
| **Web UI** | ✅ Modern Next.js with real-time tree + lane views, optional auth, Vercel/Docker/Render-ready | ✅ Next.js dashboard |
| **Report formats** | ✅ MD + PDF (WeasyPrint) + DOCX | ✅ MD + PDF + DOCX |
| **Inline images** | ✅ Flux + Grok + SD providers, cached | ❌ |
| **MCP (Model Context Protocol) client** | ✅ stdio + HTTP transports, read-only gate, env interpolation | ❌ |
| **Claude Skill** | ✅ ships at `skills/agent-orchestra/` | ❌ |
| **VS Code extension** | ✅ Full extension with live debate panel | ❌ |
| **Tracing** | ✅ LangSmith / Langfuse / OTLP, opt-in | ✅ LangSmith |
| **Templates** | ✅ 18 certified, YAML-first | 🟡 Report types only |
| **Three-tier deploy** | ✅ Demo / Local Ollama / Cloud BYOK | ✅ Local / Cloud |
| **Docker image** | ✅ multi-stage, ghcr | ✅ |
| **License** | Apache-2.0 | Apache-2.0 |

## Where Orchestra is stronger

- **Safety gate.** The Lucas veto runs as a separate `grok-4.20-0309`
  pass with strict-JSON output and fail-closed defaults. Malformed
  JSON, low confidence, or timeout → exit 4 → nothing ships.
- **Visible debate.** Four role lanes stream live in role-coloured
  bubbles. The debate is the product, not just the means.
- **YAML-first.** Every run is a checked-in spec. Reproducible without
  remembering CLI flags.
- **Templates as first-class artefacts.** 18 certified templates with
  a machine-readable index for downstream marketplaces.
- **Mix-and-match providers.** Cheaper Harper + strict Lucas in the
  same run is one YAML edit away.

## Where GPT-Researcher is stronger

- **Maturity.** Older project, larger community, more deployment
  recipes in the wild.
- **Search backends.** Built-in support for more search providers
  out-of-the-box.
- **Frontend polish.** Next.js dashboard with richer interactions.

## When to pick which

| You want… | Pick |
| --- | --- |
| A safety gate you can prove to compliance | Orchestra |
| The Grok native multi-agent endpoint | Orchestra |
| Reproducible YAML specs in version control | Orchestra |
| The most mature OSS option today | GPT-Researcher |
| The richest frontend out-of-the-box | GPT-Researcher |
| Both — pipe Orchestra's MD into GPT-Researcher's reader | Both |

## Head-to-head benchmark

The numbers below come from the harness at
[`benchmarks/harness.py`](https://github.com/agentmindcloud/grok-agent-orchestra/tree/main/benchmarks)
against the 12-goal corpus in `benchmarks/goals.yaml`. Methodology
is locked in
[`benchmarks/methodology.md`](https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/benchmarks/methodology.md);
the LLM-as-judge is a non-Grok model (default
`anthropic/claude-sonnet-4-6`) so we never grade ourselves.

_No public benchmark run has landed yet. The harness ships in
[`benchmarks/`](https://github.com/agentmindcloud/grok-agent-orchestra/tree/main/benchmarks);
real numbers populate this section the next time the recurring
workflow at `.github/workflows/benchmarks.yml` lands a green run with
the four required secrets configured. Until then, the methodology
link above is the contract; what follows is whatever
`benchmarks/results/latest.md` currently holds (empty in the
pre-launch state)._

{%
  include-markdown "../../benchmarks/results/latest.md"
  start="## Headline numbers"
  rewrite-relative-urls=false
%}

## See also

- [Quickstart](../getting-started/quickstart.md) — get a real run going.
- [Templates](../guides/templates.md) — the 18 certified YAMLs.
- [Blog → round-1 writeup](../blog/2026-04-orchestra-vs-gpt-researcher.md)
