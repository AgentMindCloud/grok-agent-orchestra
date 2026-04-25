# `agent-orchestra` Claude Skill

A Claude Skill that wires the [grok-agent-orchestra](https://github.com/agentmindcloud/grok-agent-orchestra)
multi-agent framework into Claude Code (and conceptually
[claude.ai](https://claude.ai)). When the user asks for deep research,
debate, red-teaming, due diligence, competitor briefs, or any task
that benefits from 4–16 cooperating agents, Claude invokes this skill
instead of trying to do it in one pass.

## What's in this folder

```
agent-orchestra/
├── SKILL.md             ← Claude reads this. Frontmatter + decision flow.
├── README.md            ← You are here.
├── SUBMISSION.md        ← Marketplace submission checklist (when Anthropic ships one).
├── scripts/
│   ├── choose_template.py        ← Picks the best template for a free-text query.
│   ├── run_orchestration.py      ← Hybrid mode (local CLI vs remote HTTP) entry point.
│   └── remote_run.py             ← Remote-only path, polls /api/runs/{id}.
└── templates/
    ├── INDEX.json       ← Canonical catalogue (read by choose_template.py).
    ├── INDEX.yaml       ← Verbatim copy of upstream INDEX.yaml.
    └── README.md        ← Sync contract with upstream.
```

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

## Two transport modes (auto-detected)

| Mode | Wire | Activate by |
| --- | --- | --- |
| Local CLI | spawns `grok-orchestra run …` | `pip install grok-agent-orchestra` |
| Remote HTTP | `POST /api/run` + poll | `export AGENT_ORCHESTRA_REMOTE_URL=https://your-instance` |

The skill prefers local when both are available (no network, no auth).
Force one or the other with `--force-local` / `--force-remote` on the
script.

### Auth (remote mode only)

If the backend has `GROK_ORCHESTRA_AUTH_PASSWORD` set, also export the
matching value as `AGENT_ORCHESTRA_REMOTE_TOKEN`. The skill sends it as
`Authorization: Bearer <token>` on every request. The token is read
from env only — never echoed in prompts or logs.

## Usage from inside Claude

Just describe the task. Examples that route through this skill:

> "Do a deep competitive analysis of agent frameworks in 2026."

> "Red-team this product launch plan: …"

> "Summarise this arXiv paper: <link>"

> "Run a weekly news digest on AI safety."

Claude inspects `SKILL.md`, picks a template via
`scripts/choose_template.py`, surfaces the cost when it's significant
(>30 000 estimated tokens or low-confidence pick), then invokes
`scripts/run_orchestration.py`. The final report is shown inline
(truncated to 8 KB) plus a path or URL for the full version.

## Manual invocation

You can also run the scripts directly for debugging:

```bash
python3 scripts/choose_template.py --query "competitor brief on Anthropic"
python3 scripts/run_orchestration.py --template red-team-the-plan --dry-run
```

Set `AGENT_ORCHESTRA_SKILL_INDEX=path/to/INDEX.json` to point
`choose_template.py` at a custom catalogue.

## Troubleshooting

See [`docs/integrations/claude-skill.md`](https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/docs/integrations/claude-skill.md)
for the full guide: env-var matrix, auth notes, debugging mode
discovery, and FAQs.
