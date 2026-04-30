# Releasing grok-agent-orchestra

This is the operator's checklist for cutting a new release of
`grok-agent-orchestra` to PyPI. The happy path is fully automated:
push a tag, GitHub Actions does the rest.

> **Decision log — flat layout.** The package lives at top-level
> `grok_orchestra/` rather than `src/grok_orchestra/`. Hatchling pins
> `packages = ["grok_orchestra"]` in `pyproject.toml`, and an end-to-end
> wheel install was verified before the first release, so the
> "imports-work-in-dev-but-not-after-install" failure mode doesn't apply.
> If a future change makes that assumption fragile, migrate to
> `src/grok_orchestra/` — the only required edits are the `[tool.hatch.build]`
> packages line and the `templates` symlink at the repo root.

## 0. One-time setup (already done — keep for reference)

PyPI trusted publishing must be configured **once** for the project. On
<https://pypi.org/manage/account/publishing/>, add a pending publisher with:

| Field | Value |
| --- | --- |
| PyPI Project Name | `grok-agent-orchestra` |
| Owner | `AgentMindCloud` |
| Repository name | `grok-agent-orchestra` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

After the first successful publish, PyPI converts the pending publisher
into a permanent one. **No PyPI API token ever needs to live in GitHub
Secrets.**

If, for some reason, OIDC trusted publishing is unavailable, see the
[Manual fallback](#manual-fallback-with-twine) section below.

## 1. Pre-flight checks (local)

From a clean `main` checkout:

```bash
# 1.1 — make sure your tree is clean and up to date
git checkout main
git pull --ff-only

# 1.2 — run the full test + lint suite
pip install -e ".[dev]"
pytest -q
ruff check .

# 1.3 — build the wheel + sdist locally and inspect them
python -m build
python -m twine check dist/*
ls -lh dist/
```

Expected output:

```
Successfully built grok_agent_orchestra-0.1.0.tar.gz
                   grok_agent_orchestra-0.1.0-py3-none-any.whl
Checking dist/grok_agent_orchestra-0.1.0-py3-none-any.whl: PASSED
Checking dist/grok_agent_orchestra-0.1.0.tar.gz:           PASSED
```

If `twine check` reports any issue, fix it before tagging.

## 2. Bump version

Single source of truth: `pyproject.toml -> [project].version`.

```bash
# Replace 0.1.0 with the new version everywhere it appears.
$EDITOR pyproject.toml grok_orchestra/__init__.py
```

The two files must match. CI does not enforce this yet (TODO), so a
quick `grep` is your friend:

```bash
grep -nE "0\\.1\\.0" pyproject.toml grok_orchestra/__init__.py
```

## 3. Update the changelog

Move everything under `## [Unreleased]` into a new dated section:

```markdown
## [Unreleased]

## [0.2.0] - YYYY-MM-DD

### Added
- ...
```

Add the matching link reference at the bottom:

```markdown
[0.2.0]: https://github.com/agentmindcloud/grok-agent-orchestra/releases/tag/v0.2.0
```

## 4. Commit, tag, push

```bash
git add pyproject.toml grok_orchestra/__init__.py CHANGELOG.md
git commit -m "chore(release): v0.2.0"
git push origin main

git tag -a v0.2.0 -m "v0.2.0"
git push origin v0.2.0
```

## 5. GitHub Actions takes over

The `publish` workflow in `.github/workflows/publish.yml` triggers on
the tag push and:

1. Checks out the tagged commit.
2. Builds an sdist + wheel with `python -m build`.
3. Validates them with `twine check`.
4. Publishes via `pypa/gh-action-pypi-publish` using OIDC — no API token
   touches the workflow.

Watch it at `https://github.com/AgentMindCloud/grok-agent-orchestra/actions`.
Roughly 2–3 minutes from tag push to "Available on PyPI".

## 6. Verify the release

In a fresh virtual environment:

> **Note while Bridge isn't on PyPI yet.** `grok-agent-orchestra`'s
> import guard requires `grok_build_bridge` at runtime, so the
> verification install needs Bridge available too. Either install the
> repo-local stub first (`pip install ./tools/bridge-stub`) or
> `pip install git+https://github.com/agentmindcloud/grok-build-bridge.git@main`
> before installing Orchestra. Drop this paragraph the day Bridge
> ships on PyPI.

```bash
python -m venv /tmp/verify-orchestra
source /tmp/verify-orchestra/bin/activate

pip install grok-agent-orchestra==0.2.0
grok-orchestra --version          # → grok-orchestra 0.2.0
grok-orchestra templates          # bundled catalog must list ≥ 10 entries
grok-orchestra --help             # subcommand list

deactivate
rm -rf /tmp/verify-orchestra
```

If any of these fail, **yank the release immediately**:

```bash
# yank — keeps the version reserved but hides it from `pip install`
pip install twine
twine yank grok-agent-orchestra==0.2.0
```

Then file an issue, fix the bug on `main`, and cut a new patch (e.g.
`v0.2.1`). PyPI versions are immutable — you cannot reupload `0.2.0`.

## Manual fallback with `twine`

Use only if OIDC publishing is broken (e.g. PyPI is down, the GitHub
Action is misconfigured, or you need to push a release from a forked
branch that the workflow won't touch).

```bash
# 1. Build the artifacts.
python -m build

# 2. Authenticate. Generate a project-scoped token at
#    https://pypi.org/manage/account/token/  and export it:
export TWINE_USERNAME=__token__
export TWINE_PASSWORD="<paste-your-pypi-token-here>"   # starts with pypi-

# 3. Sanity-check then upload.
python -m twine check dist/*
python -m twine upload dist/*
```

Never commit the token. Revoke and rotate after every manual upload.

## TestPyPI dry-run (optional)

Before cutting a real release, you can publish to <https://test.pypi.org/>
to validate the metadata without burning a real version number on PyPI:

```bash
python -m build
python -m twine upload --repository testpypi dist/*

pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  grok-agent-orchestra==0.2.0
```

The `--extra-index-url` flag is required because TestPyPI does not
mirror runtime dependencies (xai-sdk, rich, …).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `twine check` reports invalid metadata | Bad `pyproject.toml` — re-run `python -m build` after fixing. |
| GitHub Action `publish` job fails OIDC handshake | Confirm the pending publisher on PyPI matches `owner/repo/workflow/environment` exactly. |
| `pip install` resolves `grok-build-bridge` from PyPI but Bridge is still a git-only dep | Bump the floor in `pyproject.toml -> dependencies` once Bridge ships its first PyPI release. |
| Tag pushed, no workflow run | The tag must match `v*.*.*`. `v0.2`, `0.2.0`, and `release-0.2` all skip the trigger. |
