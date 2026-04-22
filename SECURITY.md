# Security policy

Grok Agent Orchestra ships two first-line defences for agent-authored
output, by design:

1. **Lucas veto** — every runtime runs `safety_lucas_veto` on the
   synthesised content before the deploy phase. The veto uses Lucas's
   contrarian system prompt on `grok-4.20-0309` at a hard-coded
   `reasoning_effort="high"` with a strict JSON output shape
   (`{safe, confidence, reasons, alternative_post?}`). The gate
   **fails closed** — malformed JSON, transport failures, and
   low-confidence approvals all resolve to `safe=False`.
2. **Bridge safety scan** — the combined runtime runs
   `grok_build_bridge.safety.scan_generated_code` over every generated
   file before handing the code to Orchestra. Unsafe scans abort the
   run unless the operator passes `--force`.

Neither layer is a substitute for judgment. If you are about to ship
agent-authored content to X or another public surface, read the
verdict panel.

## Supported versions

Until v1.0, only the current minor series (`0.1.x`) receives security
updates.

| Version      | Supported         |
|--------------|-------------------|
| `0.1.x`      | ✅                |
| `< 0.1`      | ❌ (pre-release)  |

## Reporting a vulnerability

Please do **not** file a public GitHub issue for security reports.

Send a report to **security@agentmind.cloud** with:

- A description of the issue and the attack surface (runtime, schema,
  CLI, dry-run path, veto, or combined flow).
- The version (`grok-orchestra --version`) and Python version.
- Reproduction steps or a minimal failing YAML.
- The impact you observed (data exposure, code execution, safety
  bypass, rate-limit amplification, etc.).

You can expect:

- Acknowledgement within **72 hours**.
- An initial assessment within **7 days**.
- Coordinated disclosure, with credit, once a fix is released.

## In scope

- Safety-veto bypass (content slipping past Lucas when it shouldn't).
- Bridge safety-scan bypass in the combined runtime.
- Prompt-injection through spec fields that execute without
  intermediate validation.
- RCE via the combined runtime's generated-code pipeline.
- Privilege escalation via tool routing (agents calling tools outside
  their declared allowlist).
- Secret leakage via streaming events or logs.

## Out of scope

- Cost amplification when operators explicitly opt into high-effort
  runs or large iteration counts — these are documented trade-offs.
- Issues in the underlying xAI API — please report upstream to xAI.
- Issues specific to downstream forks of Grok Build Bridge.

## Hardening tips for operators

- Keep `safety.lucas_veto_enabled: true`. The veto is the hero safety
  feature; disabling it is a playground-only mode.
- Set `safety.confidence_threshold ≥ 0.80` for anything that ships to
  X. The `0.75` default is sensible for drafts.
- For combined runs, review Bridge's `scan_generated_code` output
  before using `--force`.
- Use `orchestra.tool_routing` to scope agents rather than granting
  full tool access by default. The `parallel-tools` pattern makes the
  scoping explicit and logs a warning on off-list tool calls.
- Store `XAI_API_KEY` in a secret manager, not `.env` in a repo that
  might be pushed publicly.
