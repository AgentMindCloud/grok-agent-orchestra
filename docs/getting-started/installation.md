# Installation

Agent Orchestra ships as a single PyPI package with feature-gated extras. Pick the
ones you need; defaults stay lean.

## Requirements

- Python 3.10, 3.11, or 3.12
- macOS / Linux / Windows
- Optional: Docker, Ollama, Tavily / OpenAI / Anthropic / Replicate / LangSmith
  keys depending on which tier you want to run

## Base install

=== "PyPI"

    ```bash
    pip install grok-agent-orchestra
    grok-orchestra --version
    ```

=== "From GitHub"

    The sibling [`grok-build-bridge`](https://github.com/agentmindcloud/grok-build-bridge)
    is also pre-PyPI today, so install both from git:

    ```bash
    pip install git+https://github.com/agentmindcloud/grok-build-bridge.git
    pip install git+https://github.com/agentmindcloud/grok-agent-orchestra.git
    ```

=== "Editable / dev"

    ```bash
    git clone https://github.com/agentmindcloud/grok-agent-orchestra.git
    cd grok-agent-orchestra
    pip install -e ".[dev]"
    ```

## Extras

| Extra        | What it adds                                                  | When you need it |
| ------------ | ------------------------------------------------------------- | ---------------- |
| `[web]`      | FastAPI dashboard, WebSocket streaming                        | Run `grok-orchestra serve` |
| `[adapters]` | LiteLLM for OpenAI / Anthropic / Ollama / Bedrock / …         | Any non-Grok model |
| `[search]`   | Tavily + httpx + trafilatura for live web research            | YAML with `sources:` |
| `[publish]`  | WeasyPrint (PDF) + python-docx (DOCX) + markdown + pygments   | Anything beyond Markdown |
| `[images]`   | Pillow + replicate (Flux) for inline report images            | YAML with `publisher.images.enabled: true` |
| `[tracing]`  | LangSmith / Langfuse / OTLP backends                          | Want spans in a real trace store |
| `[js]`       | Playwright + Chromium (~300 MB)                               | Sites that need JS rendering |

Combine as needed:

```bash
pip install 'grok-agent-orchestra[web,adapters,search,publish]'
```

## Run in Docker

Pre-built multi-arch images live on GitHub Container Registry:

```bash
docker pull ghcr.io/agentmindcloud/grok-agent-orchestra:latest
docker run --rm -p 8000:8000 \
  -e XAI_API_KEY="<paste-yours-here>" \
  ghcr.io/agentmindcloud/grok-agent-orchestra:latest
```

For a worked walk-through, see the [Docker deploy guide](../deploy/docker.md).

## Bring your own key

Every credential is read from the environment. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
$EDITOR .env
```

The framework never embeds, ships, transmits, or logs raw values. For each
provider, see the provider's own console for where to obtain a key.

## Verifying your install

```bash
grok-orchestra --version
grok-orchestra doctor          # which tier(s) are configured right now
grok-orchestra templates       # 18 bundled starter templates
grok-orchestra --help          # full subcommand list
```
