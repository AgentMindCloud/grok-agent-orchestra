# Render

[Render](https://render.com) deploys the GHCR image as a Web Service
in three clicks.

## Service config

| Setting | Value |
| --- | --- |
| **Type** | Web Service |
| **Image** | `ghcr.io/agentmindcloud/grok-agent-orchestra:v0.1.0` |
| **Port** | `8000` |
| **Health check path** | `/api/health` |
| **Region** | nearest to your users |
| **Instance** | Starter (512 MB) is enough for simulated runs; Standard (2 GB) for cloud-tier reports. |

## Environment variables

Add at minimum:

- `XAI_API_KEY` (or `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`)
- `GROK_ORCHESTRA_WORKSPACE=/var/data` *(plus a Render Disk mounted at `/var/data`)*

Optional:

- `TAVILY_API_KEY` — web search
- `REPLICATE_API_TOKEN` — image generation
- `LANGSMITH_API_KEY` — tracing

!!! tip "Render env-var groups"
    Put all keys in a Render env-var group so the same set syncs to
    preview deploys and production.

## Persistent disk

Add a Render Disk:

| Setting | Value |
| --- | --- |
| **Mount path** | `/var/data` |
| **Size** | 1 GB (templates + cached images + run.json archives) |

## render.yaml

Drop this in your repo root for one-click "blueprint" deploys:

```yaml
services:
  - type: web
    name: grok-orchestra
    runtime: image
    image:
      url: ghcr.io/agentmindcloud/grok-agent-orchestra:v0.1.0
    healthCheckPath: /api/health
    envVars:
      - key: XAI_API_KEY
        sync: false
      - key: GROK_ORCHESTRA_WORKSPACE
        value: /var/data
    disk:
      name: orchestra-ws
      mountPath: /var/data
      sizeGB: 1
```

## See also

- [Docker](docker.md) — what the image contains.
- [Fly.io](fly.md) — alternative managed deploy.
