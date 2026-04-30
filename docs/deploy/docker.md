# Docker

The fastest path to a working dashboard — no Python install on the
host. Pre-built multi-arch images (`linux/amd64` + `linux/arm64`) ship
to **GitHub Container Registry** on every release.

## Pull and run

```bash
docker pull ghcr.io/agentmindcloud/grok-agent-orchestra:latest
docker run --rm -p 8000:8000 \
  -e XAI_API_KEY=<your-key> \
  ghcr.io/agentmindcloud/grok-agent-orchestra:latest
# → http://localhost:8000
```

The image binds to `0.0.0.0:8000` by default, runs as the unprivileged
`orchestra` user, and ships a `/api/health` HEALTHCHECK so `docker ps`
reports container readiness.

!!! warning "Pin a tag in production"
    `:latest` is fine for evals, but production should track an
    explicit `:v0.1.0` (or `:0.1`) tag so the image you ship in CI
    matches what you smoke-tested.

## Build from source

```bash
git clone https://github.com/agentmindcloud/grok-agent-orchestra.git
cd grok-agent-orchestra
cp .env.example .env                # paste XAI_API_KEY (optional for simulated runs)
docker compose up --build
```

Hot-reload during development:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

Smoke-test:

```bash
./scripts/docker-smoke-test.sh           # macOS / Linux
.\scripts\docker-smoke-test.ps1          # Windows
```

## Environment variables

| Var | Required | Notes |
| --- | --- | --- |
| `XAI_API_KEY` | for cloud tier | Bring your own key. |
| `OPENAI_API_KEY` | optional | Per-role override. |
| `ANTHROPIC_API_KEY` | optional | Per-role override. |
| `TAVILY_API_KEY` | optional | Web search. |
| `REPLICATE_API_TOKEN` | optional | Flux image generation. |
| `LANGSMITH_API_KEY` / `OTEL_*` | optional | Tracing. |
| `GROK_ORCHESTRA_WORKSPACE` | optional | Where runs/reports/cache land. Default `~/.grok-orchestra`. |

## Persistence

Mount a volume to keep workspace state across container restarts:

```bash
docker run --rm -p 8000:8000 \
  -e XAI_API_KEY=<your-key> \
  -v orchestra-ws:/home/orchestra/.grok-orchestra \
  ghcr.io/agentmindcloud/grok-agent-orchestra:latest
```

## Frontend bundled into the image

The published image bakes a static export of the Next.js dashboard at
``/app/static`` (Dockerfile&rsquo;s ``frontend`` build stage). The FastAPI
process serves the export at ``/`` and falls back to the v1 Jinja
dashboard (always available at ``/classic``) if the export is missing
— so a one-port deploy gives you both layers with no extra config.

To run with the modern frontend pointed at a remote backend instead,
deploy the frontend to [Vercel](vercel.md) and set
``NEXT_PUBLIC_API_URL`` to the published Docker container&rsquo;s URL.

## Auth

To require a shared password before runs / WebSockets are accepted,
set:

```bash
docker run --rm -p 8000:8000 \
  -e XAI_API_KEY=<your-key> \
  -e GROK_ORCHESTRA_AUTH_PASSWORD=<a-strong-password> \
  ghcr.io/agentmindcloud/grok-agent-orchestra:latest
```

When that env var is set, the bundled frontend renders ``/login``
before any other route and stores an HttpOnly session cookie on
success. Without it the dashboard is open — the local-development
default. See [`docs/architecture/extending.md`](../architecture/extending.md)
for the threat model.

## See also

- [Vercel](vercel.md) — frontend-only managed deploy that talks to a
  remote backend.
- [Render](render.md) — managed deploy.
- [Fly.io](fly.md) — global edge deploy.
