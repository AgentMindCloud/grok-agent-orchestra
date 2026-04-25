---
name: agent-orchestra
description: Run grok-agent-orchestra multi-agent orchestrations (deep research, debate, red-teaming, due diligence, competitive analysis, paper summaries, news digests, deep multi-step research workflows) via the local `grok-orchestra` CLI or a remote FastAPI backend. Use when the user asks for rigorous, sourced, multi-perspective output that benefits from 4-16 cooperating agents instead of a single LLM pass.
when_to_use: User wants a deeply-researched report, a multi-perspective debate, an adversarial red-team review, an investor memo, a competitor brief, an arXiv paper summary, a weekly news digest, or any task framed as "have multiple agents argue / research / critique X". Skip for one-shot Q&A or pure code generation.
allowed-tools: Bash
---

# Agent Orchestra

Multi-agent research with **visible debate** and **enforceable safety
veto** — powered by Grok. Four named roles (Grok / Harper / Benjamin /
Lucas) argue, then Lucas's strict-JSON pass either approves or vetoes
the synthesis before it ships.

## When to invoke this skill

Trigger phrases (non-exhaustive):

- "deep research", "deep dive", "comprehensive analysis"
- "red-team this plan", "stress-test this idea"
- "due diligence", "investor memo"
- "competitive analysis", "competitor brief"
- "summarise this paper", "summarise this arXiv"
- "weekly news digest", "news roundup"
- "debate", "policy debate", "iterative consensus"
- "fact-check with citations", "auditable analysis"

Skip for: one-shot Q&A, code generation, simple summarisation of a
single short document.

## Workflow

Run these steps in order. **Every step is a single Bash invocation** —
do not interleave other tools between mode discovery and execution.

### 1. Mode discovery

```bash
command -v grok-orchestra >/dev/null && echo "LOCAL_AVAILABLE=1" || echo "LOCAL_AVAILABLE=0"
[ -n "$AGENT_ORCHESTRA_REMOTE_URL" ] && echo "REMOTE_AVAILABLE=1 ($AGENT_ORCHESTRA_REMOTE_URL)" || echo "REMOTE_AVAILABLE=0"
```

Decision matrix:

| Local | Remote | Action |
| --- | --- | --- |
| ✅ | — | Use local CLI (preferred — no network, no auth). |
| ❌ | ✅ | Use remote FastAPI. |
| ❌ | ❌ | Stop. Tell the user: install via `pip install grok-agent-orchestra` or set `AGENT_ORCHESTRA_REMOTE_URL`. |

### 2. Template selection

If the user named a template (any of the 18 slugs in
`templates/INDEX.json`), skip to step 3. Otherwise:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/choose_template.py \
  --query "<exact paraphrase of user's task>"
```

Parse the JSON. The response shape is `{ok, top: {slug, confidence, estimated_tokens, ...}, alternates: [...]}`.

**Confirm with the user before running** when:

- `top.confidence < 0.6` (ambiguous query — show them the top + alternates and ask which fits).
- `top.estimated_tokens > 30000` (premium / long-form template — surface the cost; the spec's anti-pattern is "don't silently consume credits").

### 3. Optional spec preview

If the user wants to see what's about to run:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/run_orchestration.py --show <slug>
```

### 4. Execute

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/run_orchestration.py \
  --template <slug> \
  [--inputs-json '{"key": "value"}'] \
  [--dry-run]
```

**For non-`--dry-run` invocations, set `timeout: 600000` on the Bash
call** — orchestrations run 30–300s typically; the default 2-minute
Bash timeout is not enough.

The script auto-routes (local vs remote) per step 1. Progress is
printed to stderr; the final stdout line is always:

```
RESULT_JSON: {"ok": bool, "success": bool, "mode": "local"|"remote",
              "slug": "...", "run_id": "...", "duration_seconds": float,
              "report_path"|"report_url": "...",
              "final_content_preview": "<truncated to 8 KB>",
              "veto_report": {...} | null,
              "exit_code": int}
```

### 5. Present the result

Read the `final_content_preview` to the user. If it ends with
`(truncated; <N> bytes total)`, mention the full report path / URL
explicitly so the user can open it.

If `veto_report.approved == false`, tell the user clearly that **Lucas
vetoed the synthesis** and surface `veto_report.reasons[]`.

### 6. Failure handling

| Exit code | Meaning | What to tell the user |
| --- | --- | --- |
| 0 | Success | Show the preview + path. |
| 2 | Config error | Read `error` from `RESULT_JSON`; usually a bad slug or missing env var. |
| 3 | Runtime error | Read `error`; common cause is provider 5xx or rate limit. Suggest `--dry-run` to re-test offline. |
| 4 | Lucas vetoed | Show `veto_report.reasons[]`; offer to re-run with a different angle. |
| 5 | Rate-limited | Suggest waiting + retry, or re-running with `--mode simulated` (offline). |
| 6 | Remote unreachable | The `AGENT_ORCHESTRA_REMOTE_URL` is set but failing. Suggest `--force-local` or `--dry-run`. |
| 7 | No mode available | Neither local CLI nor remote configured. Print the install hint from the script's `error.hint`. |

## Safety

- **Cost surfaced before consumption.** Always show `estimated_tokens`
  + ask for confirmation when it exceeds 30 000 OR confidence is
  below 0.6.
- **No raw secrets in prompts.** The skill never echoes
  `AGENT_ORCHESTRA_REMOTE_TOKEN` or any provider key.
- **Lucas veto = hard stop.** Treat exit 4 as a refusal — do not try
  to re-render the blocked content as a workaround.
- **Read-only by default.** The skill only invokes `grok-orchestra
  run` / `dry-run` / `templates show`. It does NOT mutate filesystem
  state outside `$GROK_ORCHESTRA_WORKSPACE` (default
  `$PWD/.agent-orchestra-workspace`).

## Reference

- Bundled scripts: `${CLAUDE_SKILL_DIR}/scripts/`.
- Template catalogue: `${CLAUDE_SKILL_DIR}/templates/INDEX.json`
  (canonical) + `INDEX.yaml` (verbatim copy of the upstream).
- Full setup guide: `docs/integrations/claude-skill.md` in the upstream
  repo (<https://github.com/agentmindcloud/grok-agent-orchestra>).
- See `README.md` and `SUBMISSION.md` in this folder for installation
  + future-marketplace submission notes.

## Examples

**User: "Do a competitive analysis of agent frameworks in 2026."**

```bash
# 1. Mode discovery (local available).
# 2. Template selection.
python3 ${CLAUDE_SKILL_DIR}/scripts/choose_template.py \
  --query "competitive analysis of agent frameworks in 2026"
# → top.slug = "competitive-analysis", confidence ~ 0.50 (close call)
# → confirm with user, then:
python3 ${CLAUDE_SKILL_DIR}/scripts/run_orchestration.py \
  --template competitive-analysis
```

**User: "Red-team this product launch plan."**

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/run_orchestration.py \
  --template red-team-the-plan \
  --inputs-json '{"plan": "<the user's plan text>"}'
```

**User: "Summarise this arXiv paper."** (offline/dry-run pattern)

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/run_orchestration.py \
  --template paper-summarizer \
  --inputs-json '{"paper_url": "<arxiv URL>"}' \
  --dry-run
```

**User: "Run the weekly news digest on AI safety."** (premium —
confirm cost first)

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/run_orchestration.py \
  --template weekly-news-digest \
  --inputs-json '{"topic": "AI safety"}'
```
