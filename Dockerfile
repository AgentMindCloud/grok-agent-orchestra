# syntax=docker/dockerfile:1.7
# -----------------------------------------------------------------------------
# grok-agent-orchestra — multi-stage container build.
#
#   Stage 1 (builder)  : python:3.11-slim + git/gcc, install everything into a
#                        portable venv at /opt/orchestra.
#   Stage 2 (runtime)  : python:3.11-slim, copy the venv across, run as a
#                        non-root user, EXPOSE 8000, ENTRYPOINT grok-orchestra.
#
# Why a venv copy instead of `pip wheel ... && pip install` in runtime?
#   - The runtime image needs no build tools (no git, no gcc) → smaller +
#     faster + smaller attack surface.
#   - One source of truth for installed packages (the venv).
#
# Why install grok-build-bridge from git?
#   - Bridge ships pre-PyPI today; it's a sibling repo. The pyproject pins
#     `grok-build-bridge>=0.1,<1`, so we install it from GitHub first then
#     install Orchestra (which finds Bridge already satisfied).
# -----------------------------------------------------------------------------

# =========================================================================== #
# Stage 1 — builder.
# =========================================================================== #

FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends git build-essential && \
    rm -rf /var/lib/apt/lists/*

# Self-contained venv that we'll copy verbatim into the runtime stage.
RUN python -m venv /opt/orchestra
ENV PATH="/opt/orchestra/bin:$PATH"

WORKDIR /build

# 1) Bridge first — pins resolved against PyPI for everything else.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install "git+https://github.com/agentmindcloud/grok-build-bridge.git@main"

# 2) Copy just the metadata to maximise layer cache hits on dep changes.
COPY pyproject.toml README.md LICENSE ./
COPY grok_orchestra ./grok_orchestra

# 3) Install Orchestra with the [web] extra. Bridge is already in the venv,
#    so the resolver leaves it alone.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ".[web]"

# Sanity-check the entry point built correctly.
RUN grok-orchestra --version


# =========================================================================== #
# Stage 2 — runtime.
# =========================================================================== #

FROM python:3.11-slim AS runtime

LABEL maintainer="AgentMindCloud <jan@agentmind.cloud>" \
      org.opencontainers.image.title="grok-agent-orchestra" \
      org.opencontainers.image.description="Multi-agent research with visible debate and enforceable safety vetoes — powered by Grok." \
      org.opencontainers.image.source="https://github.com/agentmindcloud/grok-agent-orchestra" \
      org.opencontainers.image.url="https://github.com/agentmindcloud/grok-agent-orchestra" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/orchestra/bin:$PATH" \
    GROK_ORCHESTRA_WORKSPACE=/app/workspace

# Non-root user "orchestra" (system uid/gid).
RUN groupadd --system orchestra && \
    useradd --system --gid orchestra --create-home --home-dir /home/orchestra --shell /sbin/nologin orchestra

# Pull the venv across — no pip / no git / no compilers in the runtime image.
COPY --from=builder /opt/orchestra /opt/orchestra

WORKDIR /app
RUN mkdir -p /app/workspace && \
    chown -R orchestra:orchestra /app /home/orchestra

USER orchestra

EXPOSE 8000

# Hits the dashboard's /api/health — proves uvicorn is up + FastAPI is wired.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; \
sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else sys.exit(1)" \
    || exit 1

ENTRYPOINT ["grok-orchestra"]
# `--no-browser` because there's nothing to open inside a container.
CMD ["serve", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
