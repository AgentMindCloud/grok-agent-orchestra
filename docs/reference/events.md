# Events

The runtime emits a typed event stream that powers the TUI, the web
dashboard, and the WebSocket API. Every event is a JSON-serialisable
dict with a `type` discriminator.

## Stream events

These come from the LLM providers themselves.

| `type` | `kind` | Carries |
| --- | --- | --- |
| `stream` | `token` | `role`, `text` — incremental output |
| `stream` | `tool_call` | `role`, `tool_name`, `tool_args` |
| `stream` | `tool_result` | `role`, `tool_name`, `result` |
| `stream` | `reasoning_tick` | `role`, `effort` (Grok native only) |
| `stream` | `error` | `role`, `error` |

## Lifecycle events

These are synthesised by the runtime and patterns.

| `type` | Carries |
| --- | --- |
| `role_started` | `role` |
| `role_completed` | `role`, `output` |
| `debate_round_started` | `round_n` |
| `lucas_passed` | `confidence` |
| `lucas_veto` | `reason`, `blocked_content` |
| `run_completed` | `final_output`, `usage` |
| `run_failed` | `error` |
| `report_exported` | `format`, `path` |
| `image_generated` | `provider`, `cost_usd`, `cached` |
| `image_failed` | `provider`, `error` |

## WebSocket frame format

`/ws/runs/{run_id}` sends one JSON frame per event:

```json
{
  "type": "role_started",
  "role": "Harper",
  "ts": "2026-04-25T12:00:00Z"
}
```

```json
{
  "type": "stream",
  "kind": "token",
  "role": "Harper",
  "text": "Researching biological computing…",
  "ts": "2026-04-25T12:00:00.030Z"
}
```

The connection closes after `run_completed` or `run_failed`.

## Late-connect replay

If a client connects mid-run, the WebSocket handler drains the bounded
replay buffer (last 2000 events) before tailing the live queue. Each
replayed event has the same shape — clients can't tell replay from live.

## Programmatic subscription

```python
def on_event(ev):
    if ev["type"] == "role_started":
        print(f"--- {ev['role']} ---")
    elif ev["type"] == "stream" and ev.get("kind") == "token":
        print(ev["text"], end="")

run_orchestra(config, client, event_callback=on_event)
```

## See also

- [Python API](python-api.md) — `event_callback` parameter.
- [Tracing](../guides/tracing.md) — every event maps to a span attribute.
