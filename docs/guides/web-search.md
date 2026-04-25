# Web search

Harper's research tool is wired through a `Source` Protocol. The default
web backend is **Tavily** — a search API that returns synthesised
answers + citation URLs.

## Setup

```bash
pip install "grok-agent-orchestra[search]"
export TAVILY_API_KEY=tvly-...
```

The framework reads `TAVILY_API_KEY` directly via the Tavily SDK's
resolver. The key is never logged, embedded, or transmitted by Agent
Orchestra itself.

??? warning "BYOK"
    No keys are bundled. `grok-orchestra doctor` reports which
    keys it found — and which tiers it can run as a result.

## Configure in YAML

```yaml
sources:
  - kind: web_search
    backend: tavily
    max_queries_per_run: 12   # hard budget; over-budget queries are skipped
    cache_ttl_hours: 24       # SQLite cache; lowers cost across re-runs
    respect_robots: true      # default; block disallowed paths
```

## Budget controls

The framework caps work in three places:

1. **Query budget** (`max_queries_per_run`) — stops the agent burning
   credits on a runaway loop.
2. **Cache** (`cache_ttl_hours`) — identical queries hit a SQLite cache
   under the workspace directory; cost-free.
3. **Robots compliance** (`respect_robots`) — `robots.txt` is fetched
   once per host per run; disallowed URLs are skipped before the fetch.

## Add another backend

The Source Protocol lives in `grok_orchestra/sources/__init__.py`. To
add Brave, Serper, or a custom corpus search, implement:

```python
class MyBackend:
    name = "my-backend"
    def query(self, q: str, *, k: int = 8) -> list[Hit]: ...
```

…and register it in `grok_orchestra/sources/providers/__init__.py`.

## See also

- [Local docs](local-docs.md) — offline alternative.
- [Tracing](tracing.md) — every search call gets its own span.
