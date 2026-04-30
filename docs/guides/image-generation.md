# Image generation

Reports can include a cover image and per-section illustrations. The
generation layer is a `ImageProvider` Protocol with three concrete
backends today and a stub for tests.

## Providers

| Provider | Status | Backend | Cost |
| --- | --- | --- | --- |
| `flux` | ✅ production | Replicate (Flux Schnell / Pro) | ~$0.003/image |
| `grok` | 🟡 stub | xAI image endpoint | TBD |
| `stub` | test-only | in-memory PNG | $0 |

`grok` raises an explicit `ImageError` pointing to `flux` until xAI
exposes a stable image endpoint. To plug in another backend, register a
factory with `register_image_provider("name", factory)`.

## Setup (Flux)

```bash
pip install "grok-agent-orchestra[images]"
export REPLICATE_API_TOKEN=r8_...
```

```yaml
publisher:
  images:
    enabled: true
    provider: flux
    budget: 3
    cover: true
    section_illustrations: 2
    style: "minimal flat illustration, monochrome"
```

## Caching

Image cost is *real* money, and identical prompts are common across
re-runs of the same template. The framework caches by:

```
sha256(provider + model + prompt + style_prefix + size)
```

Cache lives at `${GROK_ORCHESTRA_WORKSPACE}/image_cache/`. A cache
hit skips the provider call entirely — `cost_usd` is recorded as `0`
in the run trace.

## Policy denylist

Prompts containing flagged terms (specific public-figure names, common
violence triggers) are refused **before** the provider call. The
refusal increments `image_refusals` in the run trace; the report
renders without that image.

The denylist lives in `grok_orchestra/images/policy.py` and is
intentionally narrow — it's a tripwire, not content moderation.
For real moderation, route through the provider's own classifier.

## Failure handling

If the provider raises (rate limit, network error, refusal), the
Publisher catches and:

1. Logs the failure as an `image_failed` span.
2. Skips the image ref in the Markdown.
3. Continues rendering the report.

A failed image **never** blocks a report from shipping.

## See also

- [Reports & export](reports-and-export.md) — where images land.
- [Tracing](tracing.md) — `image_generation` span kind.
