# Observability

Tracing is **off by default**. The framework ships with a zero-overhead
`NoOpTracer` so unset runs are byte-for-byte identical in latency to
the pre-Prompt-10 codepath.

Set ONE of the following env vars to opt in. The rest of this document
explains what gets traced, how the scrubber works, and how to wire each
backend.

## Backends

| Backend   | Activator env var(s)                                      | Library             |
| --------- | --------------------------------------------------------- | ------------------- |
| LangSmith | `LANGSMITH_API_KEY`                                       | `langsmith`         |
| OTLP      | `OTEL_EXPORTER_OTLP_ENDPOINT`                             | `opentelemetry-sdk` |

Resolution order is the order above — first matching backend wins.
Install the optional extras with:

```bash
pip install 'grok-agent-orchestra[tracing]'
```

**Bring your own key.** The framework reads credentials from the
environment (or `.env`) only. Keys never appear in logs, never appear
in span attributes, never cross provider boundaries.

## Quick start

```bash
export LANGSMITH_API_KEY="<paste-your-key-here>"
export LANGSMITH_PROJECT=grok-agent-orchestra
grok-orchestra trace info       # confirm backend selected
grok-orchestra trace test       # emit a synthetic 2-span run
grok-orchestra serve            # next dashboard run gets a "View trace" link
```

## Span hierarchy

Every Orchestra run produces this tree:

```
run                                kind=run
├── debate_round_1                 kind=debate_round
│   ├── role_turn/Grok             kind=role_turn (model=…, tokens_in/out, cost_usd)
│   │   ├── llm_call               kind=llm_call (provider=…)
│   │   └── tool_call/web_search   kind=tool_call (when sources: is set)
│   ├── role_turn/Harper           kind=role_turn
│   ├── role_turn/Benjamin         kind=role_turn
│   └── role_turn/Lucas            kind=role_turn
├── lucas_evaluation               kind=lucas_evaluation
│   └── veto_decision              kind=veto_decision (status=passed|blocked, reasons[])
└── publisher                      kind=publisher (added when a report is exported)
    ├── markdown_render            kind=markdown_render
    ├── pdf_render                 kind=pdf_render
    └── docx_render                kind=docx_render
```

Captured on every span (subject to the scrubber):

- `inputs` — system + role messages, request body
- `outputs` — model reply or render artefact summary
- `tokens_in` / `tokens_out` / `cost_usd` (when the provider reports usage)
- `model` / `provider` / `mode` (from Prompt 9)
- `latency_ms` (set automatically by the context manager)
- `error` (on failure)
- `veto_decision` only: `approved`, `confidence`, `reasons[]`, `blocked_claim`

## Scrubber

Every span passes through
[`grok_orchestra.tracing.scrubber.Scrubber`](../grok_orchestra/tracing/scrubber.py)
before it leaves the box. The default config redacts:

- **Credential patterns** — `sk-…`, `tvly-…`, `xai-…`, `pypi-…`,
  `ghp_…`, `hf_…`, `AKIA…`, `AIza…`, `Bearer …`. These get replaced
  with `[REDACTED]` in-line; surrounding prose is preserved.
- **Sensitive field names** — keys whose lowercase form contains any
  of `api_key`, `secret`, `password`, `authorization`, `bearer`,
  `access_token`, `refresh_token`, `session_token`, `private_key`,
  `x-api-key`, `x-subscription-token`. The *value* is redacted; the
  *name* stays so debuggers can see which field was scrubbed.
- **Long strings** — anything over 4 KiB is hard-truncated and the
  tail replaced with `…[truncated N chars]`.

Operators can extend the deny list (`Scrubber(deny_field_substrings=…)`)
or whitelist a field that *looks* sensitive but isn't
(`allow_field_substrings=["public_session_id"]`). Custom regexes can
be supplied via `extra_patterns`.

The scrubber is **always on** for every backend tracer. There is no
way to disable it short of editing the source — that's intentional.

## Sampling

LangSmith reads `LANGSMITH_SAMPLE_RATE` (default `1.0`). The decision
is made at the *root span* — once a root is sampled in, every child
is captured; once it's sampled out, the whole tree is dropped.

OTLP sampling is delegated to the collector (configure on the
receiving side).

## Failures

Tracing is **best-effort**. Any backend failure (network down, rate
limit, malformed payload) logs at WARNING level and the run continues.
A misconfigured tracer never crashes a run.

## CLI

```bash
grok-orchestra trace info                   # which backend is live + sampling config
grok-orchestra trace test                   # emit a synthetic run; print deep-link URL
grok-orchestra trace export <run-id>        # dump events.json for offline review
```

`trace export` reads the snapshot the dashboard wrote at
`$GROK_ORCHESTRA_WORKSPACE/runs/<run-id>/run.json` — it works even
when no live tracer is configured.

## Roadmap

- A "Lucas vetoes I shipped this week" SQL view derived from the
  veto_decision span. (Prompt 12.)
- Image-generation spans (`kind="image_generation"`) — already
  reserved in the SpanKind literal. (Prompt 11.)
- Per-tier dashboards. The doctor-command JSON output is the contract
  the dashboard will index on.
