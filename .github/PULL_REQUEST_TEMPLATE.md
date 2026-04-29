<!--
Thanks for the PR. The checklist below mirrors the items in
`CONTRIBUTING.md`. Anything you can pre-tick saves a triage round.
For one-line typo fixes, the checklist is overkill — feel free to
delete it and just describe the fix.
-->

## Summary

<!-- One paragraph: what changes, and why. Link the issue if there is
one (`Closes #N` / `Refs #N`). -->

## Test plan

<!-- How a reviewer can verify locally. Bullet points are fine. -->

- [ ] `pytest -q` green locally.
- [ ] `ruff check .` clean.
- [ ] (UI/docs touch) `mkdocs build --strict` clean.

## Checklist

- [ ] New or changed code has tests in the matching `tests/test_*.py`.
- [ ] CHANGELOG entry added under `[Unreleased]`.
- [ ] CLI surface change → `python scripts/gen_cli_docs.py` re-run.
- [ ] New public API → Google-style docstring (used by mkdocstrings).
- [ ] No secrets in the diff (no API keys, no `.env` files).
- [ ] Bridge contract preserved — anything imported from
      `grok_build_bridge.*` keeps its current shape, or
      `docs/integrations/build-bridge.md` updated.
- [ ] Lucas safety-veto path still fail-closed if `safety_veto.py`
      changed.
