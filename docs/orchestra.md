# Orchestra — Design Notes

> Stub. Full design doc lands in Session 12.

Grok Agent Orchestra provides two interchangeable execution backends for
Grok 4.20 multi-agent workflows:

1. **Native** (`runtime_native`) — dispatches to the xAI multi-agent endpoint
   (`grok-4.20-multi-agent-0309`) and returns aggregated role outputs.
2. **Simulated** (`runtime_simulated`) — orchestrates a prompt-driven debate
   between named roles (Grok the planner, Harper the researcher, Benjamin the
   implementer, Lucas the safety reviewer) over a single-agent Grok endpoint.

Both backends share:

- The Bridge `XAIClient` for HTTP/auth.
- The Bridge `audit_x_post` safety primitive.
- The Orchestra `safety_veto.LucasVeto` gate for agent-authored side effects.
- The Orchestra `patterns` library for hierarchical, dynamic, debate-loop,
  parallel, and recovery flows.

The `dispatcher` chooses between backends based on `ORCHESTRA_MODE`
(`native` | `simulated` | `auto`). The `combined` runtime layers Orchestra on
top of a live Bridge session so both can share tool state.
