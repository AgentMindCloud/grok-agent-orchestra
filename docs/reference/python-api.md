# Python API

Agent Orchestra is a library first, a CLI second. Everything the CLI
does is a thin wrapper around `run_orchestra(config, client)`.

## Quick example

```python
from grok_orchestra import parse_yaml, run_orchestra
from grok_orchestra.dispatcher import resolve_client

config = parse_yaml(open("spec.yaml"))
client = resolve_client(config)             # pick provider from YAML
result = run_orchestra(config, client)

print(result.final_output)
print(result.veto_report)                   # {approved, confidence, reasons}
print(result.usage)                         # {tokens_in, tokens_out, cost_usd}
```

## Streaming events

Pass a callback to receive events as the run progresses:

```python
def on_event(ev):
    print(ev.kind, ev.role, getattr(ev, "text", ""))

run_orchestra(config, client, event_callback=on_event)
```

See [Events](events.md) for the full event taxonomy.

## Provider modules

### Sources

::: grok_orchestra.sources
    options:
      show_root_heading: false
      members:
        - Source
        - Hit

### LLM clients

::: grok_orchestra.llm
    options:
      show_root_heading: false
      members:
        - LLMClient
        - resolve_client

### Image providers

::: grok_orchestra.images
    options:
      show_root_heading: false
      members:
        - ImageProvider
        - GeneratedImage
        - ImageError
        - resolve_image_provider

### Tracer

::: grok_orchestra.tracing
    options:
      show_root_heading: false
      members:
        - Tracer
        - SpanKind
        - resolve_tracer

### Publisher

::: grok_orchestra.publisher.Publisher
    options:
      show_root_heading: true
