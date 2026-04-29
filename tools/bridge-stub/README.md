# `grok-build-bridge` CI stub

A minimal installable shim that satisfies Orchestra's `grok-build-bridge`
runtime dependency in environments where the **real** Bridge package
isn't available — namely:

- The MkDocs / mkdocstrings job that needs to import `grok_orchestra.*`
  to render API reference pages.
- The `pip-audit` safety-scan job (indirectly — see below).
- Any one-off contributor sandbox that wants to run docs builds without
  cloning Bridge.

It is **not** a functional implementation of Bridge. Every entry point
is a no-op or a placeholder return value mirroring
`tests/conftest.py`'s in-memory stubs. The wheel registers as
`grok-build-bridge==0.1.0+stub` so `pip install` calls satisfying
`grok-build-bridge>=0.1,<1` succeed without reaching PyPI.

## Install

```bash
pip install ./tools/bridge-stub
pip install -e .              # Orchestra resolves Bridge from the stub
```

## When to delete

Once the real `grok-build-bridge` package lands on PyPI:

1. Drop the `pip install ./tools/bridge-stub` lines from
   `.github/workflows/{ci,docs}.yml`.
2. Remove the `grok-build-bridge` filter in the safety-scan job.
3. Delete this directory.

The contributor docs explicitly recommend installing the **real**
Bridge for development (`docs/integrations/build-bridge.md`); the stub
is CI plumbing only.
