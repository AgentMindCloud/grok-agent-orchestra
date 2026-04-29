# Contributing to Agent Orchestra

Thanks for considering a contribution. Agent Orchestra is small enough
that most fixes land in a single PR — this doc is the short version.

> **Heads-up:** Agent Orchestra is a **[Grok Build Bridge](https://github.com/agentmindcloud/grok-build-bridge)
> add-on**. You'll need Bridge installed in your dev environment for
> the test suite to pass. See
> [`docs/integrations/build-bridge.md`](docs/integrations/build-bridge.md).

## Setup

```bash
git clone https://github.com/agentmindcloud/grok-agent-orchestra
cd grok-agent-orchestra
python -m venv .venv && source .venv/bin/activate
pip install grok-build-bridge                       # required first
pip install -e ".[dev,web,publish,images,tracing,docs-build,search,adapters,mcp]"
```

Verify:

```bash
pytest -q                    # all tests pass
ruff check .                 # clean
mkdocs build                 # docs site builds
```

## Repo layout

```
grok_orchestra/         Python package — runtime, patterns, sources, publisher,
                        web, llm, tracing, images, workflows
benchmarks/             Head-to-head harness vs GPT-Researcher (offline-friendly)
docs/                   MkDocs Material site
extensions/vscode/      VS Code extension (TypeScript + esbuild)
frontend/               Next.js 14 dashboard (App Router + Tailwind + shadcn/ui)
skills/agent-orchestra/ Claude Skill (SKILL.md + Python scripts)
tests/                  pytest suite — every external service mocked
```

## Hard rules

- **BYOK.** Never embed, ship, or transmit a key. Read from env via
  the provider SDK's own resolver. Tests must mock — no live API
  calls in CI.
- **Lucas is fail-closed.** If you touch `safety_veto.py`, malformed
  JSON / low confidence / timeout must still exit 4.
- **Don't break the four roles.** Grok / Harper / Benjamin / Lucas
  are the canonical names. Templates and tests assume them.
- **Don't break the Bridge contract.** Anything Orchestra imports
  from `grok_build_bridge.*` must keep its current shape; flag
  breakage in the integration guide before changing.
- **No `--no-verify` commits.** If a hook fails, fix the trigger,
  don't bypass.

## Branch naming

Use scope/short-slug:

```
feat/mcp-server-postgres
fix/lucas-veto-timeout
docs/build-bridge-mode-b-example
chore/bump-litellm-1.42
```

## Commit message convention

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)
— same shape as everything else in the repo's history:

```
<type>(<scope>): <imperative summary, ≤72 chars>

Optional body explaining the WHY. Reference issues with
`Closes #N` / `Refs #N`. Co-author lines welcome.
```

Common types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`,
`perf`, `ci`.

## PR checklist

- [ ] `pytest -q` green locally.
- [ ] `ruff check .` clean.
- [ ] New code has tests in the matching `tests/test_*.py` file.
- [ ] CLI surface change → `python scripts/gen_cli_docs.py` re-run.
- [ ] New public API → Google-style docstring (used by mkdocstrings).
- [ ] CHANGELOG entry under `[Unreleased]`.
- [ ] No secrets in the diff.
- [ ] Bridge-touching changes → update
      [`docs/integrations/build-bridge.md`](docs/integrations/build-bridge.md).

## Where to discuss before big changes

- Open a [GitHub Discussion](https://github.com/agentmindcloud/grok-agent-orchestra/discussions)
  for "should we…?" questions.
- Open an [Issue](https://github.com/agentmindcloud/grok-agent-orchestra/issues)
  for "this is broken / I want X" requests.
- Large refactors without a tracking issue are likely to be asked to
  split.

## How to add a new role / template / source / provider

| Adding a… | Read first | Pattern |
| --- | --- | --- |
| Template | [`docs/guides/templates.md`](docs/guides/templates.md) | YAML in `grok_orchestra/templates/<slug>.yaml` + entry in `INDEX.yaml` + test in `tests/test_templates_certified.py` |
| Source backend | [`docs/architecture/extending.md`](docs/architecture/extending.md) | Subclass `Source`; register; mock-test under `tests/test_sources_*.py` |
| LLM provider | [`docs/guides/multi-provider-llm.md`](docs/guides/multi-provider-llm.md) | Add to `grok_orchestra/llm/registry.py`; LiteLLM does most providers already |
| Image provider | [`docs/guides/image-generation.md`](docs/guides/image-generation.md) | Subclass `ImageProvider`; register; mock the SDK |

## Code of Conduct

By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md). Report violations to
`conduct@agentmind.cloud`.

## License

Apache-2.0. Contributions are accepted under the same.
