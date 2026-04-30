# v0.1.0 — Bridge-paired launch

First public release. Grok Agent Orchestra turns a single YAML into a Grok
4.20 multi-agent run — either xAI-native (`grok-4.20-multi-agent-0309`) or a
visible prompt-simulated debate between **Grok / Harper / Benjamin / Lucas** —
with a real safety veto before anything ships.

**Pairs with [Grok Build Bridge](https://github.com/agentmindcloud/grok-build-bridge).** Install
Bridge first, Orchestra second.

## Install

```bash
# 1. Bridge (paired runtime)
pip install git+https://github.com/agentmindcloud/grok-build-bridge.git@main

# 2. Orchestra (this release)
pip install git+https://github.com/AgentMindCloud/grok-agent-orchestra.git@v0.1.0

# Or use the Docker image (multi-arch, runs as non-root):
docker pull ghcr.io/agentmindcloud/grok-agent-orchestra:v0.1.0
```

PyPI listing arrives once Trusted Publishing is provisioned — see
`docs/RELEASING.md`.

## What's in the box

- **CLI + Python library** — `grok-orchestra run|combined|validate|templates|init|debate|veto|version`.
- **Two runtimes**: native xAI multi-agent and prompt-simulated debate.
- **Five orchestration patterns**: hierarchical, dynamic-spawn, debate-loop, parallel-tools, recovery.
- **Combined Bridge + Orchestra runtime** with one continuous live panel.
- **Lucas safety veto** with strict-JSON output, fails closed.
- **Ten certified templates** + a JSON schema for IDE completions.
- **FastAPI server** with optional shared-password auth (off by default).
- **Next.js dashboard** for live debate visualisation (sideload-deployable; `/classic` Jinja UI also bundled).
- **VS Code extension** (sideload `.vsix` until v1.x marketplace publish).
- **Two tracing backends** that work today: LangSmith and OTel/OTLP.
- **Docker image** — multi-arch (amd64 + arm64), non-root user, healthcheck wired.
- **Public benchmarks** vs GPT-Researcher under `benchmarks/`.

## Removed (pre-launch tidy-up)

- `BraveProvider`, `BingProvider`, `SerpAPIProvider` (search) and `StableDiffusionProvider`
  (image) shipped as skeletons that raised on first use. Removed to keep the public surface
  honest. The plug-in interface is unchanged — register your own via `@register_provider` /
  `register_image_provider`.
- `LangfuseTracer` — broke at install time due to `packaging<25` vs xAI SDK's `>=25,<26`.
  LangSmith and OTel cover the supported tracing surface. Langfuse 3.x adapter is queued
  for a later release.

## Quickstart

```bash
grok-orchestra init red-team-the-plan -o my-run.orchestra.yaml
export XAI_API_KEY="..."
grok-orchestra run my-run.orchestra.yaml
```

Try `grok-orchestra templates` for the catalogue and `grok-orchestra debate "your goal"`
for an ad-hoc debate.

## Verification

- 527 tests passing, 82.4% coverage on the gated subset.
- Multi-arch Docker image built on this tag.
- Schema-validated against every bundled template.
- `pip-audit` clean on all runtime dependencies.

## What's next (v0.1.x roadmap)

- PyPI publish (one-time OIDC click + manual `workflow_dispatch`).
- VS Code Marketplace listing once screenshots are captured (currently sideload-only).
- Bridge migrates to PyPI → drop the `tools/bridge-stub` shim.

See [`CHANGELOG.md`](CHANGELOG.md) for the full diff and the
[`SECURITY.md`](SECURITY.md) policy for responsible disclosure.

---

**Pair it with Bridge, write a YAML, watch the debate.**
