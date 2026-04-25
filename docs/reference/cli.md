# CLI reference

`grok-orchestra` is the single entry point. Every command is a Typer
sub-command; everything supports `--help` for the live reference.

!!! tip "Auto-generated from `--help`"
    Run `python scripts/gen_cli_docs.py` in your dev checkout to
    regenerate this file straight from `grok-orchestra <cmd> --help`.
    Use the live `--help` in your terminal as the source of truth —
    this page is a curated overview.

## Top-level commands

| Command | Purpose |
| --- | --- |
| `grok-orchestra version` | Print the package version and exit. |
| `grok-orchestra doctor` | Probe Local + Cloud tiers; report which are ready. |
| `grok-orchestra init <template>` | Copy a bundled template into the working dir. |
| `grok-orchestra validate -f <spec>` | Schema-validate a YAML spec without running it. |
| `grok-orchestra dry-run -f <spec>` | Replay scripted stream from canned events — no API calls. |
| `grok-orchestra run -f <spec>` | Run a spec with live providers. |
| `grok-orchestra orchestrate <spec>` | Run a Bridge + Orchestra combined spec. |
| `grok-orchestra export <run-id>` | Render `report.{md,pdf,docx}` from a stored run. |
| `grok-orchestra serve` | Start the FastAPI web dashboard. |

## Sub-apps

### `grok-orchestra templates`

```bash
grok-orchestra templates list                   # grouped by category
grok-orchestra templates list --tag debate
grok-orchestra templates list --format json
grok-orchestra templates show <slug>            # print YAML
grok-orchestra templates copy <slug> [dest]     # copy to dest (default ./<slug>.yaml)
```

### `grok-orchestra models`

```bash
grok-orchestra models list                      # show resolved provider chain
grok-orchestra models test --provider xai --model grok-4-0709
```

### `grok-orchestra trace`

```bash
grok-orchestra trace info                       # which backend is active
grok-orchestra trace test                       # emit a synthetic 2-span run
grok-orchestra trace export <run-id>            # write trace JSON for a run
```

## Global options

These work on every command:

| Flag | Effect |
| --- | --- |
| `--no-color` | Disable colour. Useful for log redirects. |
| `--log-level {DEBUG,INFO,WARNING,ERROR}` | Set logger level. |
| `--json` | Emit machine-readable JSON summary at exit. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success. |
| 1 | Generic failure. |
| 2 | Configuration error (missing key, malformed YAML). |
| 3 | Runtime error (provider 5xx, network). |
| 4 | Lucas vetoed the output — `safe=false`. |

## See also

- [YAML schema](yaml-schema.md) — what `validate` accepts.
- [Events](events.md) — what `serve` streams over WebSocket.
- [Python API](python-api.md) — call from your own code.
