# Reports with inline images

Run a real orchestration that ends with a report carrying an
auto-generated cover + section illustrations — like GPT-Researcher's
Gemini-image flow, but with a per-template budget, a configurable
policy layer, and an on-disk cache.

## One-time setup

```bash
pip install 'grok-agent-orchestra[adapters,publish,images]'
export REPLICATE_API_TOKEN="<paste-yours-here>"
grok-orchestra doctor                 # confirm tier readiness
```

## Run

```bash
grok-orchestra run examples/with-images/illustrated-research.yaml
open $GROK_ORCHESTRA_WORKSPACE/runs/<run-id>/report.pdf
```

## Where the images go

Each image lands at:

```
$GROK_ORCHESTRA_WORKSPACE/runs/<run-id>/images/
    cover.png
    findings.png
    analysis.png
    ...
```

The cache lives at:

```
$GROK_ORCHESTRA_WORKSPACE/.cache/images/<sha256>.{png,json}
```

A second run with the same `(provider, model, prompt, style, size)` is a
free cache hit.

## Switching providers

The default is `flux` (Flux.1 schnell on Replicate). Other options:

- `provider: grok` — placeholder; raises a clear error pointing back to
  Flux until xAI ships a stable image API.

## Policy reminders

- The framework refuses prompts that name real public figures or
  copyrighted characters by default.
- The default style prefix discourages realistic faces / real people.
- `publisher.images.deny_terms` extends the refusal list per template.
- A single image failure logs a WARNING and the report ships without
  that section's illustration — the report never blocks on image
  generation.

## Cost panel

The `Run.image_stats` field surfaces on `/api/runs/{id}` and the
dashboard's run-detail panel:

```json
{
  "max_images": 4,
  "images": 3,
  "cache_hits": 1,
  "cache_misses": 2,
  "total_cost_usd": 0.006,
  "refusals": 0
}
```
