# Build Bridge

Agent Orchestra is a [Grok Build Bridge](https://github.com/agentmindcloud/grok-build-bridge)
add-on. Bridge is the runtime that turns a YAML spec into generated
code, scans it, and ships it; Orchestra is what you bolt on when you
want the thinking part of that pipeline to be a visible, named-role
debate with an enforceable safety veto.

This page is the canonical "how do I use them together?" guide.

## Why pair them

Bridge alone gives you:

- A YAML-driven generator (`grok-build-bridge run spec.yaml`).
- A safety scanner over the generated artefacts.
- A deploy step.

Orchestra adds:

- Four named roles (Grok / Harper / Benjamin / Lucas) with separate
  prompts, models, and tool budgets.
- A streaming debate TUI you can show to a stakeholder.
- A **fail-closed** Lucas veto with strict-JSON output and exit code
  4 on any failure mode (malformed JSON, low confidence, timeout).
- A reproducible event trail (`orchestra-events.jsonl`) you can hand
  to a third-party auditor.

The two tools share `XAIClient`, `audit_x_post`, `scan_generated_code`,
the Rich console, and the deploy plumbing — Orchestra deliberately
doesn't reimplement any of those.

## Install order

Bridge first, Orchestra second:

```bash
pip install grok-build-bridge
pip install grok-agent-orchestra
```

Order matters: Orchestra's `__init__.py` imports
`grok_build_bridge.safety.audit_x_post` and
`grok_build_bridge.xai_client.XAIClient` at import time and raises a
`RuntimeError` with a clear hint if Bridge is missing.

> **Pre-launch heads-up.** Bridge is on the path to PyPI but the
> first published wheel may lag this page. Until then, install Bridge
> from the GitHub source tree (`pip install
> git+https://github.com/agentmindcloud/grok-build-bridge`) or
> point at the in-tree CI shim at `tools/bridge-stub/` for a no-op
> install (docs build / type-check only — see the README in that
> directory).

## Two integration modes

There are exactly two supported wiring shapes.

### Mode A — Bridge-led (the documented hook)

You're driving Bridge, you want Lucas to gate the final deploy.
This is the integration the Bridge docs explicitly call out. One
line of YAML:

```yaml
# my-build.yaml — Bridge spec
name: x-trend-analyzer
version: 0.1.0

build:
  prompt: |
    Generate a Python module that fetches yesterday's most-discussed
    X topics and returns a structured summary.

deploy:
  target: stdout

safety:
  lucas_veto_enabled: true   # ← the entire integration
```

Run it with Bridge as usual:

```bash
grok-build-bridge run my-build.yaml
```

When the deploy gate fires, Bridge calls into Orchestra's
`safety_lucas_veto` instead of (or in addition to) its own scan.
Lucas exits 4 on `block` / malformed JSON / low confidence / timeout
and the deploy never happens. No code changes on either side; the
flag does the wiring.

Pick this mode when:

- You started with `grok-build-bridge init` and built outward.
- The headline of your YAML is the artefact, not the debate.
- You want the lightest-touch safety upgrade.

### Mode B — Orchestra-led (the combined runtime)

You're driving Orchestra, you want Bridge's generate + scan + deploy
as supporting cast around the multi-round debate. The flag here is
on the Orchestra spec:

```yaml
# my-orchestra.yaml — Orchestra spec
name: combined-trendseeker
version: "1"

combined: true                # ← turns on the combined runtime

goal: |
  Surface the day's most-discussed tech topic on X, draft a 3-tweet
  thread about it, and only ship if Lucas signs off twice.

build:                        # Bridge phase
  prompt: |
    Generate a lightweight scraper module for X trends.
  output_dir: ./generated

pattern: debate-then-veto     # Orchestra phase
roles:
  grok:    { model: grok-4.20-multi-agent-0309 }
  harper:  { model: grok-4.20-fast }
  benjamin:{ model: grok-4.20-fast }
  lucas:   { model: grok-4.20-0309, veto_threshold: 0.8 }

deploy:
  target: stdout              # Bridge ships
```

Run it through Orchestra:

```bash
grok-orchestra orchestrate my-orchestra.yaml
```

The implementation is at `grok_orchestra/combined.py`
(`run_combined_bridge_orchestra`). The phases — Bridge generate →
Bridge scan → Orchestra debate → Lucas veto → Bridge deploy — render
inside a single `DebateTUI` so the user sees one continuous show.
Two bundled examples: `combined-trendseeker.yaml` and
`combined-coder-critic.yaml` under `grok_orchestra/templates/`.

Pick this mode when:

- The debate is the headline; codegen is the supporting cast.
- You want a single artefact (`bridge.manifest.json` +
  `orchestra-events.jsonl`) covering the whole pipeline.
- You're showing the run to a non-technical stakeholder and the role
  lanes are the value prop.

## Shared contract

Both modes inherit the same operational contract:

| Concern | Shared between Bridge and Orchestra |
| --- | --- |
| Env vars | `XAI_API_KEY`, `X_BEARER_TOKEN` (when posting to X) |
| Exit codes | `0` success / `2` config error / `3` runtime error / `4` safety veto |
| CLI flags | `--dry-run`, `--force`, `--verbose` |
| Logger | `grok_build_bridge._console.console` (Rich, shared) |

`--force` lets a flagged Bridge scan through but **never** lets a
Lucas veto through. That's intentional — Lucas is the gate the user
asked for.

## What Orchestra imports from Bridge

These are the load-bearing imports:

```python
from grok_build_bridge import _console
from grok_build_bridge.builder import generate_code
from grok_build_bridge.deploy import deploy_to_target
from grok_build_bridge.parser import BridgeConfigError, load_yaml
from grok_build_bridge.safety import audit_x_post, scan_generated_code
from grok_build_bridge.xai_client import XAIClient
```

**Stability caveat.** These are not yet a documented public API —
Bridge is on its alpha → 0.2 → 1.0 line. Orchestra pins
`grok-build-bridge>=0.1,<1` in `pyproject.toml` to stay inside the
0.x major. Any Bridge-side breakage in those names is a release-blocker
for both projects; Bridge contributors should flag changes in the
[`docs/integrations/build-bridge.md`](https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/docs/integrations/build-bridge.md)
PR description.

## Troubleshooting

**`RuntimeError: grok-agent-orchestra requires grok-build-bridge…`**
&nbsp; Bridge isn't installed in the active interpreter. Run
`pip show grok-build-bridge`. If it prints `Package(s) not found`,
install Bridge into the same venv before re-running.

**Mode A doesn't seem to call Lucas.**
&nbsp; Check `safety.lucas_veto_enabled: true` is present in the
Bridge YAML and is at the top level of the `safety` block. Bridge
prints `[orchestra] Lucas veto requested` to the run log if the hook
fired.

**Mode B exits 4 with no obvious veto.**
&nbsp; The Lucas veto JSON parsed but failed the confidence floor.
Re-run with `--verbose` — the veto verdict prints the score, the
threshold, and the reasoning bullet that pushed it over. If the
threshold is too tight, `roles.lucas.veto_threshold` in the YAML
controls it.

**`bridge.manifest.json` shows up but `orchestra-events.jsonl`
doesn't.**
&nbsp; You ran Mode A — only the Bridge artefact is written. Mode B
writes both side-by-side under the run directory.

## See also

- [Build Bridge homepage](https://agentmindcloud.github.io/grok-build-bridge/)
- [Build Bridge CLI reference](https://agentmindcloud.github.io/grok-build-bridge/reference/cli/)
- [Orchestra CLI reference](../reference/cli.md)
- The two combined templates:
  [`combined-trendseeker.yaml`](https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/grok_orchestra/templates/combined-trendseeker.yaml)
  and
  [`combined-coder-critic.yaml`](https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/grok_orchestra/templates/combined-coder-critic.yaml).
