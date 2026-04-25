# Contributing

Thanks for considering a contribution. Agent Orchestra is small enough
that most fixes land in a single PR — this page is the short version.

## Setup

```bash
git clone https://github.com/agentmindcloud/grok-agent-orchestra.git
cd grok-agent-orchestra
python -m venv .venv && source .venv/bin/activate
pip install -e ".[adapters,publish,images,tracing,docs-build,web,search,dev]"
```

Verify:

```bash
pytest -q                    # 412+ tests, all green
ruff check .                 # clean
mkdocs build --strict        # docs site builds
```

## Repo layout

```
grok_orchestra/
  cli.py                  # Typer entry point
  dispatcher.py           # run_orchestra(config, client, ...)
  parser.py               # YAML → typed config
  patterns.py             # native | debate-loop | dynamic-spawn | …
  runtime_native.py       # xAI native multi-agent endpoint runtime
  runtime_simulated.py    # multi-call orchestration over LiteLLM
  safety_veto.py          # Lucas
  multi_agent_client.py   # MultiAgentEvent + clients
  llm/                    # LLMClient Protocol + factory
  sources/                # Source Protocol + factory
  images/                 # ImageProvider Protocol + factory
  tracing/                # Tracer Protocol + 3 backends + scrubber
  publisher/              # MD + PDF + DOCX rendering
  web/                    # FastAPI + WebSocket + dashboard
  templates/              # 18 certified YAML templates + INDEX.yaml
docs/                     # MkDocs Material site
tests/                    # everything mocked, no live calls
```

## Hard rules

- **BYOK.** Never embed, ship, or transmit a key. Read from env via
  the provider SDK's own resolver. Tests must mock — no live API
  calls in CI.
- **Lucas is fail-closed.** If you touch `safety_veto.py`, malformed
  JSON / low confidence / timeout must still exit 4.
- **Don't break the four roles.** Grok / Harper / Benjamin / Lucas
  are the canonical names. Templates and tests assume them.
- **No `--no-verify` commits.** If a hook fails, fix the hook trigger,
  don't bypass.

## PR checklist

- [ ] `pytest -q` passes locally.
- [ ] `ruff check .` clean.
- [ ] New code has tests in the matching `tests/test_*.py` file.
- [ ] If you changed the CLI surface, re-run `python scripts/gen_cli_docs.py`.
- [ ] If you added a public API, add a docstring (Google style — used by mkdocstrings).
- [ ] CHANGELOG entry under `[Unreleased]`.

## Talk to us

- File an issue: <https://github.com/agentmindcloud/grok-agent-orchestra/issues>
- Discuss before big changes — large refactors without a tracking
  issue are likely to be asked to split.

## See also

- [Releasing](releasing.md) — how a new version cuts.
- [Code of conduct](code-of-conduct.md) — expectations.
- [Architecture → Extending](../architecture/extending.md) — adding a
  source / provider / pattern.
