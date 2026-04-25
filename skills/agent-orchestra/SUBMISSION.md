# Marketplace submission notes

Anthropic does not (yet) run a public Claude Skills marketplace. When
they do, this file is the single place to paste / regenerate
submission metadata from. Until then, users install via
`cp -R skills/agent-orchestra ~/.claude/skills/`.

## Submission metadata (ready to paste)

- **Skill name:** `agent-orchestra`
- **Display name:** Agent Orchestra
- **Version:** mirrors `grok-agent-orchestra` (currently 1.0.0).
- **Maintainer:** AgentMindCloud (<https://github.com/agentmindcloud>)
- **License:** Apache-2.0 (matches the upstream framework).
- **Source URL:** <https://github.com/agentmindcloud/grok-agent-orchestra/tree/main/skills/agent-orchestra>
- **One-line summary:** Multi-agent research with visible debate and
  enforceable safety vetoes — powered by Grok.
- **Long description:** see `description` + `when_to_use` in
  `SKILL.md`'s frontmatter (under the 1 536-character cap).
- **Categories:** Research, Analysis, Multi-agent, Safety, Developer
  Tools.
- **Required tools:** `Bash`.
- **Required environment:** Python ≥ 3.10 (stdlib only — no pip deps
  for the skill scripts themselves).
- **Optional environment:**
  - `pip install grok-agent-orchestra` for local CLI mode.
  - `AGENT_ORCHESTRA_REMOTE_URL` for remote HTTP mode.
  - `AGENT_ORCHESTRA_REMOTE_TOKEN` (when the backend has auth on).
- **Network access:** outbound HTTP to the user-configured
  `AGENT_ORCHESTRA_REMOTE_URL` only. No third-party services.
- **Privacy:** the skill never exfiltrates the user's prompt or
  artefacts to anywhere other than the configured backend (local
  process or the URL the user set).

## Submission checklist (when the marketplace ships)

- [ ] All four scripts run without modification on macOS, Linux,
      WSL with system Python 3.10+.
- [ ] `python3 scripts/run_orchestration.py --show <slug>` returns 0
      for every slug listed in `templates/INDEX.json`.
- [ ] `pytest tests/test_skill_*.py` is green on the upstream main.
- [ ] `INDEX.json` is byte-equivalent to the upstream
      `grok_orchestra/templates/INDEX.yaml`
      (verified by `tests/test_skill_index_in_sync.py`).
- [ ] `SKILL.md` frontmatter `description` + `when_to_use` ≤ 1 536
      chars combined.
- [ ] Screenshots (3): mode discovery, template confirm, final report.
- [ ] Demo video (≤ 60 s): one full red-team-the-plan run end-to-end.
- [ ] Privacy + security disclosures match this file.

## Updating the bundled catalogue

The skill ships a static copy of `templates/INDEX.yaml` (+ JSON
translation) so it doesn't need to hit the upstream repo at install
time. Update via:

```bash
cp grok_orchestra/templates/INDEX.yaml \
   skills/agent-orchestra/templates/INDEX.yaml
python -c "import yaml, json; \
  d = yaml.safe_load(open('grok_orchestra/templates/INDEX.yaml')); \
  json.dump(d, open('skills/agent-orchestra/templates/INDEX.json', 'w'), \
            indent=2, sort_keys=False)"
pytest tests/test_skill_index_in_sync.py -q
```

CI fails on drift — see `tests/test_skill_index_in_sync.py`.
