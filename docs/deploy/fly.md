# Fly.io

[Fly.io](https://fly.io) runs the GHCR image globally with a single
TOML and `flyctl deploy`.

## fly.toml

Drop this into your repo root:

```toml
app = "grok-orchestra"
primary_region = "iad"

[build]
  image = "ghcr.io/agentmindcloud/grok-agent-orchestra:v0.1.0"

[env]
  GROK_ORCHESTRA_WORKSPACE = "/data"
  PORT = "8000"

[[services]]
  internal_port = 8000
  protocol = "tcp"

  [[services.ports]]
    port = 80
    handlers = ["http"]
    force_https = true

  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]

  [services.concurrency]
    type = "requests"
    hard_limit = 25
    soft_limit = 20

  [[services.http_checks]]
    interval = "10s"
    grace_period = "30s"
    method = "get"
    path = "/api/health"
    protocol = "http"
    timeout = "2s"

[mounts]
  source = "orchestra_ws"
  destination = "/data"

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 512
```

## Deploy

```bash
fly launch --copy-config --no-deploy
fly volumes create orchestra_ws --size 1
fly secrets set XAI_API_KEY=<your-key>
fly secrets set TAVILY_API_KEY=<your-tavily-key>      # optional
fly secrets set REPLICATE_API_TOKEN=<your-replicate>  # optional
fly deploy
```

## Multi-region

```bash
fly regions add lhr fra syd
fly scale count 3 --max-per-region 1
```

Each region gets a local replica; the persistent volume is per-region
so each replica has its own `runs/` cache. The workspace is the only
state — losing a region replica drops in-flight runs but no historical
reports unless you've configured external storage.

## See also

- [Docker](docker.md) — image contents and env vars.
- [Render](render.md) — alternative managed deploy.
