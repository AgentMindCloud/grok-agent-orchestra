# Launch posts

Drafts only. The author reviews each post before it goes out. Every
`{{HEADLINE_*}}` placeholder is filled from the latest run of the
benchmark harness — see [`benchmarks/render_report.py`](../../benchmarks/render_report.py)
for the substitution logic when we wire it up; for now, fill them
in manually after running `python -m benchmarks.harness`.

The numbers below are placeholders until the first benchmark run
lands. Do **not** post until they're real.

---

## X / Twitter — 10-post thread

> **1/** Multi-agent research with **visible debate** and an
> **enforceable safety veto** is now a thing you can install.
>
> 🟠 v1.0 of Agent Orchestra ships today. Apache-2.0. CLI + web UI
> + Claude Skill + VS Code extension.
>
> 🧵 with the receipts ↓

> **2/** The opinion: single-agent research is convenient, but the
> debate that makes a report worth reading happens *between* agents.
>
> Orchestra spins up four named roles (Grok / Harper / Benjamin /
> Lucas) and shows you the entire argument. No black box.

> **3/** **Lucas is the gate.**
>
> A separate `grok-4.20-0309` pass with strict-JSON output and
> fail-closed defaults. Malformed JSON, low confidence, or timed-
> out → exit code 4 → nothing ships. The default safety story isn't
> a content moderation API — it's a model that argues with the model.

> **4/** Today we also publish round 1 of a head-to-head benchmark
> against [@assafelovic](https://twitter.com/assafelovic)'s
> gpt-researcher.
>
> 12 goals × 4 domains. Third-party LLM-as-judge (Claude Sonnet,
> not Grok — see methodology). Full per-goal table is public.

> **5/** Where Orchestra wins:
>
> 📊 **{{HEADLINE_AUDIT_LINES_PER_DOLLAR}}× more audit lines per
> dollar** vs gpt-researcher-default
>
> 🎯 **{{HEADLINE_FACTUAL_SCORE_DELTA}} pp higher factual score**
> on the contested-research goals (where the judge thinks the
> argument matters)

> **6/** Where Orchestra **doesn't** win — and we publish those
> rows too:
>
> 💸 GPT-Researcher is cheaper per one-shot summary
> ⚡ GPT-Researcher is faster on shallow goals
>
> Different tools for different jobs. The whole table is in the docs.

> **7/** Other things you didn't have until today:
>
> 🛒 18 certified templates (research, debate, business, code-review)
> 🔌 LiteLLM adapter — Grok native OR OpenAI / Anthropic / Ollama / …
> 🌐 MCP (Model Context Protocol) client — plug your private repos /
>    DBs / docs in
> 🧪 Deep-research workflow with recursive sub-question planning

> **8/** And the surfaces:
>
> 🖥 Modern Next.js 14 dashboard (courtroom-style debate viz)
> 💬 Claude Skill — `~/.claude/skills/agent-orchestra/`
> 🛠 VS Code extension — right-click YAML → Run with Agent Orchestra
> 🐳 Multi-arch Docker on GHCR

> **9/** The whole thing is BYOK + fail-closed-by-default + Apache-
> 2.0. It pairs with Build Bridge (the runtime under it) and the
> [adapters] extra lets you point Harper / Benjamin at a local
> Ollama model so only Lucas burns cloud credits.
>
> Code: github.com/agentmindcloud/grok-agent-orchestra
> Docs: agentmindcloud.github.io/grok-agent-orchestra

> **10/** Re-running the benchmark monthly. New goals as the field
> shifts. Every result has a downloadable trace.
>
> If you ship multi-agent stuff and want to be in round 2, drop a
> link to your default config and we'll run you against the same
> 12 goals.

---

## Hacker News — Show HN

**Title**

> Show HN: Multi-agent research with visible debate and enforceable
> vetoes — head-to-head benchmark vs GPT-Researcher

**Body**

Hi HN —

I've been frustrated by single-agent research tools since we started
building one ourselves. The output quality plateaued, and the bug I
couldn't fix was that you couldn't *see* why the report came out the
way it did. So we built Agent Orchestra around a visible four-role
debate (Grok / Harper / Benjamin / Lucas), a separate strict-JSON
veto pass that fails closed, and a docs surface that publishes the
whole audit trail.

Today we're shipping v1.0 with: a CLI, a Next.js 14 dashboard with
the courtroom-style debate viz, a Claude Skill, a VS Code extension,
multi-arch Docker, optional MCP integration, optional auth,
LangSmith / Langfuse / OTLP tracing, and an offline mode (Ollama).
18 certified YAML templates ship in the box.

What I'd really like feedback on is the **benchmark methodology**:

- 12 goals across tech / finance / science / operations.
- Four systems-under-test: Orchestra (Grok native), Orchestra
  (LiteLLM/OpenAI), gpt-researcher (default), gpt-researcher (deep).
- Third-party LLM-as-judge (Claude Sonnet by default — explicitly
  *not* Grok or Lucas, to avoid same-model bias).
- Metrics: tokens, cost, wall, citations, unique domains, audit lines
  per dollar, factual score against curated references, hallucination
  rate (claims without supporting citation in a ±2-sentence window).
- We **publish losing rows**. GPT-Researcher is cheaper for one-shot
  summarisation; we don't hide that.
- The judge has documented inter-rater calibration (≥ 0.78 on
  citation-relevance on the 0-3 scale). Below 0.5 triggers a re-run.

Round 1 numbers (median across the 12 goals):

- {{HEADLINE_AUDIT_LINES_PER_DOLLAR}}× more audit lines per dollar
  vs gpt-researcher-default.
- {{HEADLINE_FACTUAL_SCORE_DELTA}} pp higher factual score on the
  contested-research goals.
- {{HEADLINE_VETOES_TRIGGERED}} of 12 runs vetoed by Lucas. Per the
  manual review (in the comparison report), the judge agreed with
  the veto on {{HEADLINE_VETOES_AGREED}} of those.

Trade-offs I want to be honest about:

- Orchestra is more expensive per run on shallow goals.
- Wall time is noisier than I'd like; we report median across a
  warm-up + measured run.
- The judge has biases. We publish the prompts.

Code: https://github.com/agentmindcloud/grok-agent-orchestra
Live methodology: https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/benchmarks/methodology.md
Round-1 report: https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/benchmarks/results/latest.md

I'd love feedback on:

1. The judge methodology. Is the rubric defensible? Should we
   ensemble judges?
2. The 12-goal set. Domains we're missing?
3. The hallucination heuristic. ±2-sentence window catches the
   common case but misses cross-paragraph claims.

---

## Reddit — r/LocalLLaMA + r/MachineLearning

**Title**

> [P] Agent Orchestra v1.0: visible multi-agent debate + safety veto
> + benchmark vs GPT-Researcher

**Body**

We just shipped v1.0 of Agent Orchestra — a multi-agent research
framework where the entire debate is on screen and a separate veto
pass either approves or blocks the synthesis. Apache-2.0.

What's interesting for r/LocalLLaMA: it runs **fully local** with
Ollama as the LLM backend (`pip install
'grok-agent-orchestra[adapters]' && ollama pull llama3.1:8b`).
Grok native is the power mode but the framework is provider-
agnostic via LiteLLM — OpenAI, Anthropic, Mistral, Cohere, Bedrock,
Azure, Ollama, vLLM, Together, Groq are all plug-and-play.

For ML folks: we shipped a head-to-head benchmark against
GPT-Researcher today. 12 goals across 4 domains, third-party
LLM-as-judge (Claude Sonnet, *not* Grok — explicit anti-pattern).
Full per-goal table is public; we don't suppress losing rows.

Round-1 medians:

- Audit lines per dollar: {{HEADLINE_AUDIT_LINES_PER_DOLLAR}}× vs
  gpt-researcher-default
- Factual score: +{{HEADLINE_FACTUAL_SCORE_DELTA}} pp on
  contested-research goals
- Hallucination rate: -{{HEADLINE_HALLUCINATION_DELTA}} pp

Re-running the benchmark monthly. The harness, the goals, and the
methodology are all in the public repo so anyone can re-run
themselves.

Repo: https://github.com/agentmindcloud/grok-agent-orchestra
Methodology: https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/benchmarks/methodology.md

---

## LinkedIn

**Headline**

> The receipts: multi-agent research vs single-agent research,
> head-to-head, with a third-party LLM judge.

**Body**

Today we shipped Agent Orchestra v1.0 — the first multi-agent
research framework with a visible four-role debate and an
enforceable strict-JSON safety veto.

We also shipped what we think is the first public head-to-head
benchmark of multi-agent vs single-agent research, scored by an
independent LLM-as-judge. 12 goals across tech, finance, science,
and operations. Four systems-under-test. Full per-goal table is
public; we don't hide the rows where we lose.

Round 1 medians:

📊 **{{HEADLINE_AUDIT_LINES_PER_DOLLAR}}× more audit lines per
dollar** vs the leading open-source competitor — the metric that
matters most when a regulator or a board asks "show me how the
report was produced".

🎯 **+{{HEADLINE_FACTUAL_SCORE_DELTA}} pp factual score** on
contested-research goals where adversarial review actually matters.

⚖ **{{HEADLINE_VETOES_TRIGGERED}} of 12 runs vetoed by Lucas** —
the safety gate. Per the published rubric, the third-party judge
agreed with the veto on {{HEADLINE_VETOES_AGREED}} of those.

Apache-2.0. BYOK. Pairs with Grok Build Bridge.

Repo: https://github.com/agentmindcloud/grok-agent-orchestra
Round-1 report: https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/benchmarks/results/latest.md
Methodology: https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/benchmarks/methodology.md

#AI #MultiAgent #LLM #OpenSource #Benchmarks
