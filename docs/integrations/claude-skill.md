# Claude Skill — `agent-orchestra`

Run Agent Orchestra orchestrations from inside Claude Code (and
conceptually claude.ai). When a user describes a deep-research /
debate / red-team task, Claude routes through this skill instead of
trying to do the work in one pass.

The skill is **fully self-contained** — it ships in this repo at
[`skills/agent-orchestra/`](https://github.com/agentmindcloud/grok-agent-orchestra/tree/main/skills/agent-orchestra)
and works in two transport modes (auto-detected):

| Mode | What it spawns | Activate by |
| --- | --- | --- |
| **Local CLI** *(preferred)* | `grok-orchestra run <slug> --json` via subprocess | `pip install grok-agent-orchestra` |
| **Remote HTTP** | `POST /api/run` + poll `GET /api/runs/{id}` | `export AGENT_ORCHESTRA_REMOTE_URL=https://your-instance` |

If both are available, local wins (no network, no auth, no token
budget surprises).

## Install

### Personal (every Claude Code session, all projects)

```bash
mkdir -p ~/.claude/skills
cp -R skills/agent-orchestra ~/.claude/skills/
```

### Project-scoped (commit alongside your code)

```bash
mkdir -p .claude/skills
cp -R skills/agent-orchestra .claude/skills/
git add .claude/skills/agent-orchestra
```

Claude Code picks up changes to `SKILL.md` immediately — no restart
needed.

## What Claude reads

The skill ships [`SKILL.md`](https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/skills/agent-orchestra/SKILL.md)
with YAML frontmatter (name + trigger description + `allowed-tools:
Bash`) and a 7-section body that walks Claude through:

1. **Mode discovery** — checks `command -v grok-orchestra` and
   `$AGENT_ORCHESTRA_REMOTE_URL`.
2. **Template selection** — runs
   `python3 ${CLAUDE_SKILL_DIR}/scripts/choose_template.py --query "<paraphrase>"`
   when the user hasn't named a template; parses the JSON.
3. **Confirm with user** — when confidence < 0.6 OR
   estimated_tokens > 30 000.
4. **Execute** — runs
   `python3 ${CLAUDE_SKILL_DIR}/scripts/run_orchestration.py --template <slug>`
   with `timeout: 600000` for non-dry-run.
5. **Read result** — parses the trailing `RESULT_JSON: {...}` line.
6. **Failure handling** — exit codes 2 / 3 / 4 / 5 / 6 / 7 mapped to
   user-readable messages.
7. **Safety** — Lucas-veto = hard stop, no retry attempts.

## Environment variables

| Var | Required | Where set |
| --- | --- | --- |
| `AGENT_ORCHESTRA_REMOTE_URL` | for remote mode | client (Claude env) |
| `AGENT_ORCHESTRA_REMOTE_TOKEN` | only when backend has auth on | client |
| `GROK_ORCHESTRA_AUTH_PASSWORD` | matches the token above | backend (FastAPI process) |
| `GROK_ORCHESTRA_WORKSPACE` | optional; defaults to `$PWD/.agent-orchestra-workspace` | client |
| `XAI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `TAVILY_API_KEY` | for live runs (vs `--dry-run`) | wherever the CLI runs |
| `AGENT_ORCHESTRA_SKILL_INDEX` | optional override for the bundled INDEX.json | client (testing only) |

The skill never echoes any of these into LLM prompts. They flow to
the subprocess / HTTP client only.

## Authentication

When the backend has `GROK_ORCHESTRA_AUTH_PASSWORD` set (the optional
shared-password gate from Prompt 16d), set the client-side
`AGENT_ORCHESTRA_REMOTE_TOKEN` to the same value. The skill sends it
as `Authorization: Bearer <token>` on every `/api/run` and
`/api/runs/...` request.

If you forget, the skill returns:

```json
{
  "ok": false,
  "error": "401 unauthorized — set AGENT_ORCHESTRA_REMOTE_TOKEN to the backend's GROK_ORCHESTRA_AUTH_PASSWORD"
}
```

…and exits 2 (config). Claude relays the message to the user.

## Cost transparency

The skill follows two rules to keep credits honest:

1. **Estimated cost is surfaced before consumption.** `choose_template.py`
   includes `estimated_tokens` in its response; the SKILL prompt asks
   Claude to confirm with the user when it exceeds 30 000.
2. **Low-confidence picks confirm with the user.** When the template
   match is < 0.6 confidence, Claude shows the top + alternates and
   asks which fits.

## Output truncation

Reports can be 50 KB+. The skill returns the first 6 KB + last 1.5 KB
inline, with `(truncated; <N> bytes total)` between them, plus the
absolute path or URL of the full report. Truncation operates on UTF-8
bytes (multi-byte safe) and avoids splitting inline image links.

## Manual invocation

For debugging or scripting outside Claude:

```bash
# Pick a template for a query
python3 skills/agent-orchestra/scripts/choose_template.py \
  --query "weekly news digest about AI safety"

# Run end-to-end (chooses local vs remote automatically)
python3 skills/agent-orchestra/scripts/run_orchestration.py \
  --template red-team-the-plan --dry-run

# Force remote and pass auth
AGENT_ORCHESTRA_REMOTE_URL=https://api.example.com \
AGENT_ORCHESTRA_REMOTE_TOKEN=hunter2 \
python3 skills/agent-orchestra/scripts/run_orchestration.py \
  --template paper-summarizer --force-remote
```

## Troubleshooting

??? note "`exit 7` / "Neither local CLI nor remote backend is available""
    Either install the CLI (`pip install grok-agent-orchestra`) or
    set `AGENT_ORCHESTRA_REMOTE_URL` to a reachable FastAPI.

??? note "`exit 4` / Lucas vetoed the synthesis"
    The veto is fail-closed by design. Inspect
    `veto_report.reasons[]` in the result; do **not** retry the same
    prompt — re-frame the question or change the template.

??? note "`exit 6` / network error"
    Remote endpoint unreachable. Try `--force-local` if the CLI is
    installed locally. Check the URL has no trailing slash issues.

??? note "Wrong template auto-picked"
    The heuristic is tuned for common phrasings but it isn't an LLM.
    Pass `--top-k 5` to see more alternates; or name the slug
    explicitly: `--template <slug>`.

## Submission to Anthropic Skills marketplace

When Anthropic ships a public skills marketplace, the bundle is
ready to submit — see
[`skills/agent-orchestra/SUBMISSION.md`](https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/skills/agent-orchestra/SUBMISSION.md)
for the metadata + checklist.

## See also

- [Skill source](https://github.com/agentmindcloud/grok-agent-orchestra/tree/main/skills/agent-orchestra)
- [CLI reference](../reference/cli.md)
- [Web API → `/api/run`](../reference/yaml-schema.md)
- [Architecture overview](../architecture/overview.md)
