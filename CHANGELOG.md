# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Headline for the next release:** *Multi-agent research that runs free on
> your laptop OR scales up with your favorite cloud LLM.*

## [Unreleased]

### Added
- **Deep Research workflow — recursive sub-question planner (Prompt 15a / 4).**
  First piece of the GPT-Researcher-style deep-research surface; pairs
  the recursive planner with this project's visible-debate +
  Lucas-veto guarantees. Lives under
  ``grok_orchestra.workflows.deep_research`` (new ``workflows``
  package; siblings will follow in 15b / 15c / 15d).
  - **``SubQuestion``** — one node in the plan tree. Carries
    ``text``, ``parent_id``, ``depth``, ``priority`` (0.0-1.0),
    ``required_sources`` (``web|local|mcp|reasoning``), ``rationale``,
    plus mutable ``status`` / ``answer`` / ``citations`` / ``error``
    fields that 15b will mutate as it executes leaves. Frozen
    enum coercion + ``to_dict`` / ``from_dict`` round-trip.
  - **``ResearchPlan``** — tree wrapper with ``all_nodes()``,
    ``leaf_nodes()``, ``find(id)``, and a per-status ``progress()``
    snapshot. Versioned via ``schema_version: 1`` so future shape
    changes can land without breaking saved plans.
  - **``Planner``** — recursive sub-question generator. One LLM call
    per node; emits ``planner_call`` events; parses strict JSON +
    leniently handles markdown fences and ``{"questions": [...]}``
    wrappers. Source routing is *per-node* — each sub-question
    declares which backends it needs, the input contract for 15b's
    dispatcher.
  - **Hard caps the YAML cannot disable**:
    ``HARD_DEPTH_CEILING=6`` and ``HARD_FANOUT_CEILING=12``.
    ``priority_threshold`` (default 0.4) marks low-priority sibs as
    ``SKIPPED`` and prunes the recursion before they spawn another
    LLM call.
  - **``DeepResearchWorkflow``** — top-level entry point. Persists
    the plan to ``$GROK_ORCHESTRA_WORKSPACE/runs/<run_id>/plan.json``
    and auto-resumes when re-run with the same ``run_id``
    (override with ``resume=False``). YAML form:

    .. code-block:: yaml

        workflow: deep_research
        goal: "What are the most promising agentic AI frameworks in 2026?"
        max_depth: 3
        max_sub_questions_per_level: 5
        priority_threshold: 0.4
        sources:
          - {type: web}
          - {type: local, path: ./workspace/docs}

  - **``LLMCallable`` injection point** — every Planner LLM hop
    routes through a ``Callable[[system, user], str]`` so tests
    pass scripted responses without touching xAI / LiteLLM /
    Bridge. ``build_default_llm_call()`` lazily binds to
    ``patterns._grok_call`` for production.
  - **Three new ``SpanKind`` values** reserved for tracing:
    ``planning_root``, ``planning_level``, ``planner_call``. The
    planner already emits the matching ``type`` events
    (``planning_root_started/completed``,
    ``planning_level_started/completed``, ``planner_call``,
    ``deep_research_planned``, ``deep_research_resumed``) so 15b's
    UI tile can render the tree live as it grows.
  - **``plan_tree_status(plan)``** returns a compact dict (no
    ``answer`` / ``citations`` payloads) sized for WebSocket frames.
  - **Tests (19 new, all green, fully mocked)**:
    ``tests/test_deep_research_planner.py`` (tree shape, depth cap,
    fan-out cap, source routing, lenient JSON parsing, event
    emission), ``tests/test_planner_pruning.py`` (priority threshold
    matrix, no recursion into skipped branches, edge thresholds),
    ``tests/test_planner_resume.py`` (round-trip JSON, workflow
    resume, ``resume=False``, partial-plan mutated-status survival,
    ``plan_tree_status`` snapshot).
  - **Hand-off note (15b):** the ``SubQuestion`` field shape is the
    contract for parallel sub-question execution. 15b should mutate
    ``status`` / ``answer`` / ``citations`` / ``answered_at`` /
    ``error`` in-place and re-save via ``save_plan`` after each
    leaf completes so mid-run crashes resume gracefully.
- **MCP (Model Context Protocol) client as a Source.**
  - New ``grok_orchestra.sources.mcp_source`` module — peer to
    ``LocalDocsSource`` and ``WebSource``. One ``MCPSource`` connects
    to one-or-many MCP servers and exposes their tools + resources
    to Harper.
  - **Transports:** ``stdio`` (subprocess), ``http`` (with Bearer
    auth), and ``websocket``. The MCP SDK is imported lazily inside
    ``grok_orchestra.sources._mcp_backend`` so the package stays
    importable without the ``[mcp]`` extra.
  - **Multi-server config** with per-server overrides for
    ``allow_mutations`` and ``allowed_roles``. One server's connect
    failure does not tank the run — its ``ServerStatus.error`` is
    recorded and the rest of the orchestra continues.
  - **Tool namespacing.** Every tool surfaces as
    ``<server-name>__<tool-name>`` so multi-server runs cannot
    collide (``github__search_issues``, ``filesystem__read_file``).
  - **Permission gates (read-only by default).** Tool names matching
    common mutation tokens (``write|create|update|delete|exec|...``,
    matched on word/underscore boundaries) are blocked unless
    ``allow_mutations: true`` opts in. A second gate restricts which
    roles may call MCP tools (default ``[Harper]``).
  - **Env interpolation** — ``${VAR}`` resolves at YAML-parse time
    inside ``MCPServerConfig.from_dict``. Resolved values flow to
    the subprocess / HTTP client only — never to Documents, briefs,
    span attributes, or LLM prompts. ``MCPServerConfig.public_dict()``
    returns a trace-safe summary with env *keys* but no values.
  - **Per-run resource cache** keyed by ``<server>::<uri>`` — multi-
    role references to the same MCP doc cost one read. Tool calls
    are not cached (side-effecting in general).
  - **Tracing.** Three new ``SpanKind`` values:
    ``mcp_connect``, ``mcp_tool_call``, ``mcp_resource_get`` (with
    ``server`` / ``transport`` / ``tool`` / ``latency_ms`` / ``bytes``
    attributes). Tool arguments and resource bodies are intentionally
    excluded — those can carry secrets.
  - ``[mcp]`` extra under ``[project.optional-dependencies]``:
    ``mcp>=1.0,<2`` + ``anyio>=4,<5``.
  - ``examples/mcp-github/spec.yaml`` and
    ``examples/mcp-filesystem/spec.yaml`` demonstrate the official
    ``@modelcontextprotocol/server-github`` and
    ``@modelcontextprotocol/server-filesystem`` integrations,
    including a commented-out multi-server block.
  - ``docs/guides/mcp.md`` covers transports, namespacing, gates,
    caching, tracing, and the security model. The architecture
    overview's main Mermaid diagram now lists ``mcp`` alongside
    ``web_search`` / ``local_docs``. Comparison table on the README
    + the docs site flips the MCP row to ✅ — closes the only
    capability gap vs hand-rolled MCP wrappers.
  - ``tests/test_mcp_source.py``, ``tests/test_mcp_permissions.py``,
    ``tests/test_mcp_yaml.py`` — 32 tests, every external call
    mocked through a ``client_factory`` injection point. No live
    MCP servers spawned in CI.
- **Full documentation site (MkDocs Material, versioned).**
  - New ``[docs-build]`` extra: ``mkdocs``, ``mkdocs-material``,
    ``mkdocs-include-markdown-plugin``, ``mkdocs-mermaid2-plugin``,
    ``mkdocstrings[python]``, ``mike``.
  - ``mkdocs.yml`` at repo root — deep-orange (Grok) palette with
    light/dark toggle, JetBrains Mono code, navigation tabs +
    sections, search suggest/share/highlight, Mermaid via
    ``mermaid2``, Python auto-docs via ``mkdocstrings``, mike
    versioning provider.
  - ``docs/`` site under: ``index.md`` hero · ``getting-started/``
    (installation, quickstart, your first orchestration) ·
    ``concepts/`` (four roles, Lucas veto with Mermaid, debate
    loop with two Mermaid diagrams, dynamic spawn with Mermaid) ·
    ``guides/`` (templates, local docs with Mermaid, web search,
    multi-provider LLM, reports & export, image generation,
    tracing — re-using ``docs/observability.md`` via include-
    markdown) · ``reference/`` (CLI, YAML schema, Python API
    via mkdocstrings on Source/LLMClient/ImageProvider/Tracer/
    Publisher, events) · ``architecture/`` (overview with main
    Mermaid diagram, extending, comparison) · ``deploy/``
    (Docker, Render, Fly.io) · ``contributing/`` (overview, code
    of conduct, releasing — include-markdown from
    ``docs/RELEASING.md``) · ``changelog.md`` (include-markdown
    from this file).
  - ``scripts/gen_cli_docs.py`` regenerates ``docs/reference/cli.md``
    by invoking ``grok-orchestra <cmd> --help`` so the docs always
    track the live CLI surface.
  - ``docs/stylesheets/extra.css`` — Grok-orange theme tweaks,
    hero card grid, Mermaid SVG transparency.
  - ``docs/assets/{logo,favicon}.svg`` — orange-gradient marks
    with four dots representing the four roles.
  - ``.github/workflows/docs.yml`` — ``mike``-based versioned
    deploy: ``main`` → ``/dev/`` rolling, ``v*`` tag →
    ``/<version>/`` plus ``/latest`` alias and default. PRs run
    ``mkdocs build --strict`` only (no publish).
  - README — added docs badge + Documentation section linking the
    Pages URL and key pages.
- **Inline images in reports (BYOK, off by default).** New
  ``grok_orchestra.images`` package + ``grok_orchestra.images_runner``
  glue mints a cover + section illustrations during the publisher
  step. Default OFF — templates opt in via:

  .. code-block:: yaml

      publisher:
        images:
          enabled: true
          provider: flux       # grok | flux | stable_diffusion
          budget: 4
          cover: true
          section_illustrations: 2
          style: "minimal flat illustration, no faces"

  - **``FluxReplicateProvider``** — default backend, BYOK
    ``REPLICATE_API_TOKEN`` (read by ``replicate``'s own resolver,
    never logged). Ballpark cost ≈ $0.003/image surfaced on the
    ``Run.image_stats`` snapshot.
  - **``GrokImageProvider``** — placeholder until xAI ships a stable
    image API. Per the anti-pattern guard, it raises ``ImageError``
    with a pointer to the Flux backend instead of silently no-opping.
  - **``StableDiffusionProvider``** — skeleton with a TODO pointing
    at the v2beta endpoint, mirroring the search-provider pattern.
  - **Policy layer** (``grok_orchestra.images.policy``) — hard
    refusal on real-public-figure names + copyrighted characters +
    a categorical deny list (deepfakes, minors, sexual content);
    style-prefix enforcement (``editorial illustration, abstract,
    minimal flat shapes, no realistic faces, no real people, no
    text`` by default; per-template override via
    ``publisher.images.style``).
  - **On-disk cache** (``$GROK_ORCHESTRA_WORKSPACE/.cache/images/``)
    keyed on ``sha256(provider, model, prompt, style, size)``. Cache
    hits return instantly with ``cost_usd=0`` and ``cached=True``.
  - **Per-run image budget** + cost / refusal / hit / miss counters
    surface on ``Run.image_stats`` and the dashboard panel.
  - **Tracing** — every image emits an ``image_generation`` span
    (the literal was already reserved in Prompt 10) carrying
    ``provider``, ``model``, ``cache_key``, ``cost_usd``,
    ``bytes``, ``cached``.
  - **Embed pipeline** — Markdown gets relative
    ``![…](images/<slug>.png)`` refs via the Jinja2 template;
    WeasyPrint PDF render passes the per-run report dir as
    ``base_url`` so relative refs resolve; ``python-docx``
    ``add_picture`` embeds inline at 6 inches wide. Pillow downsamples
    images > 1024 px on the longest side so PDFs stay slim.
  - **Web layer** — new ``GET /api/runs/{id}/images`` (list) and
    ``GET /api/runs/{id}/images/{name}.png`` (file) endpoints with a
    path-traversal guard. The dashboard run-detail panel grows a
    thumbnail gallery that hides itself when no images shipped.
  - **`[images]` extra** — ``Pillow>=10,<12`` + ``replicate>=0.25,<2``.
    ``.env.example`` gains ``REPLICATE_API_TOKEN`` (Flux) and
    ``STABILITY_API_KEY`` (SD skeleton) under a new
    "Inline image generation in reports" section.
  - **`examples/with-images/illustrated-research.yaml`** + companion
    README — full setup checklist and an honest-tradeoffs section.
- **39 new tests** — ``tests/test_image_policy.py`` (refusals +
  style enforcement), ``tests/test_image_providers_mock.py`` (Grok
  stub raises with Flux pointer; Flux end-to-end with mocked
  ``replicate.run`` + URL fetcher; auth / shape / failure paths;
  StableDiffusion skeleton raises),
  ``tests/test_image_cache.py`` (deterministic key, hit / miss /
  overwrite / clear / corrupt-metadata / workspace env honour),
  ``tests/test_publisher_with_images.py`` (Markdown emits cover +
  section refs; disabled / budget=0 short-circuits; provider crash
  doesn't break the report; refusals counted; cache hits across
  runs; DOCX embeds an actual ``word/media/*`` entry).

### Added
- **Optional tracing layer (BYOK, off by default).** New
  ``grok_orchestra.tracing`` package exposes a narrow ``Tracer``
  Protocol + ``SpanContext`` context-manager; ``NoOpTracer``
  (default) is zero-overhead so unset runs are byte-for-byte
  identical. Three concrete backends, all lazy-imported behind a new
  ``[tracing]`` extra (``langsmith``, ``langfuse``,
  ``opentelemetry-{api,sdk}``):
  - ``LangSmithTracer`` — selected when ``LANGSMITH_API_KEY`` is set.
    Maps every span to a LangSmith Run, preserves parent-child
    relationships, surfaces a deep-link via
    ``tracer.trace_url_for(run_id)``. Honours ``LANGSMITH_PROJECT`` +
    ``LANGSMITH_SAMPLE_RATE`` (root-only sampling).
  - ``LangfuseTracer`` — selected when ``LANGFUSE_PUBLIC_KEY`` +
    ``LANGFUSE_SECRET_KEY`` are set. Routes root spans →
    ``trace``, ``llm_call`` kind → ``generation``.
  - ``OTelTracer`` — selected when
    ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set. Targets any OTLP-compatible
    collector.
- **Span hierarchy** added at every meaningful boundary: ``run`` (root,
  carries ``mode_label``, ``provider_costs``, ``role_models``, Lucas
  verdict), ``debate_round_N``, ``role_turn`` (with ``tokens_in``,
  ``tokens_out``, ``cost_usd``, ``provider``, ``model``),
  ``lucas_evaluation`` → ``veto_decision`` (with ``approved``,
  ``confidence``, ``reasons[]``, ``blocked_claim``), and ``publisher``
  → ``markdown_render`` / ``pdf_render`` / ``docx_render``.
- **PII / secret scrubber** (`grok_orchestra.tracing.scrubber`) runs
  on every span before transit. Default config redacts known
  credential patterns (``sk-…``, ``tvly-…``, ``xai-…``, ``pypi-…``,
  ``ghp_…``, ``hf_…``, ``AKIA…``, ``AIza…``, ``Bearer …``) and
  sensitive field names (``Authorization``, ``*_API_KEY``,
  ``*_SECRET_KEY``, ``*_TOKEN``). Strings over 4 KiB hard-truncate.
  Operators can extend via ``Scrubber(deny_field_substrings=…,
  allow_field_substrings=…, extra_patterns=…)``.
- **`grok-orchestra trace` CLI subgroup** — ``info`` (active backend
  + selectors + config), ``test`` (emit a synthetic run + print
  deep-link), ``export <run-id>`` (dump events JSON from
  ``$GROK_ORCHESTRA_WORKSPACE/runs/<id>/run.json``).
- **Run dataclass + dashboard** — ``Run.trace_url`` surfaces on
  ``/api/runs/{id}`` when a backend is live; the run-results panel
  renders a **🔭 View trace** button that deep-links to the backend's
  UI for that run.
- **Failure semantics**: every backend swallows errors at WARNING
  level; a misconfigured tracer falls back to ``NoOpTracer`` and the
  user's run never breaks. ``.env.example`` gains the four supported
  env-var blocks (LangSmith / Langfuse / OTLP) under an
  "Observability (optional)" section.
- ``docs/observability.md`` — full reference covering backends,
  span hierarchy, scrubber config, sampling, failure modes, and the
  ``trace`` CLI surface. README gains a brief "Observability" section
  with a screenshot placeholder.
- **31 new tests** — ``tests/test_tracing_noop.py`` (zero-overhead
  contract + dispatcher integration), ``tests/test_tracing_langsmith.py``
  (mocked client, span shape, parent-child, scrubber applied to
  inputs, sampling, deep-link URL, backend-failure-does-not-crash-run),
  ``tests/test_scrubber.py`` (token-pattern redaction, field-name
  redaction, 4 KiB truncation, recursion across list/tuple/Mapping,
  custom allow / deny / extra patterns).

### Added
- **Three-tier capability matrix in the README** (Demo / Local Ollama
  / Cloud BYOK), with an honest tradeoffs section and a per-tier
  capability checklist. The framework now markets the local Ollama
  path explicitly — `grok-orchestra doctor` tells the user which
  tiers their machine has live right now.
- **`grok-orchestra doctor` CLI** — single-command environment
  self-check. Probes `localhost:11434` (1-second timeout, stdlib
  ``urllib.request`` so no `[search]` extra needed) for an Ollama
  server and lists installed models; checks env-var presence (never
  the value) for `XAI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`
  / `MISTRAL_API_KEY` / `GROQ_API_KEY` / `TOGETHER_API_KEY`; prints
  a Rich panel (or JSON via `--json`) with a "next step" prompt
  matched to the available tiers.
- **`examples/local-only/local-research.yaml`** — every role pinned to
  `ollama/llama3.1:8b`, `mode: simulated`, hierarchical pattern, no
  external tools. The "it works on your laptop with zero cloud cost"
  demo template. Companion `examples/local-only/README.md` walks
  through Ollama install + `ollama pull` + the adapter extra and
  closes with the three-tier escape ladder (Demo → Local → Cloud,
  including a mixed-mode middle ground).
- **GPT-Researcher comparison row** highlighting "Runs free on your
  laptop (Ollama, no keys)" — they technically support it; we
  document and smoke-test it.

### Added
- **Pluggable LLM providers via LiteLLM (BYOK).** New
  ``grok_orchestra.llm`` module exposes an ``LLMClient`` Protocol +
  provider-neutral ``ChatChunk`` / ``ChatResponse`` / ``ToolCall`` /
  ``Usage`` dataclasses. ``GrokNativeClient`` wraps the existing
  ``OrchestraClient`` (zero-overhead delegation — the Grok-native fast
  path is unchanged); ``LiteLLMClient`` lazy-imports ``litellm`` for
  every other provider (OpenAI / Anthropic / Ollama / Bedrock / Azure
  / Together / Groq / …). New ``[adapters]`` extra pulls in
  ``litellm>=1.34``; the package never embeds keys and reads every
  credential from env via LiteLLM's own resolver.
- **YAML model overrides** — top-level ``model:`` sets a global
  default; ``orchestra.agents[].model`` pins per-role; alternative
  ``orchestra.roles.<name>.model`` shape is also accepted; YAML-level
  ``model_aliases:`` map (e.g. ``fast → openai/gpt-4o-mini``) resolves
  with cycle protection. Schema's ``AgentMeta`` gains an optional
  ``model`` field.
- **Mode detection.** ``OrchestraResult`` gains ``mode_label``
  (``native`` / ``simulated`` / ``adapter`` / ``mixed``) plus
  ``role_models`` + per-provider ``provider_costs`` (USD,
  via ``litellm.cost_per_token``). The dispatcher coerces
  ``pattern: native`` to the simulated runtime when any role pins a
  non-Grok model so the multi-agent endpoint is never invoked
  off-Grok.
- **`grok-orchestra models list / test` CLI** — ``list`` shows
  the framework default + spec-defined aliases + per-role pins;
  ``test --model=…`` issues a tiny BYOK connectivity check.
  Friendly install / env-var hints when the credential is missing;
  raw key values are never logged.
- **37 new tests** — ``tests/test_llm_resolution.py`` (model-string
  routing, alias chains + cycles, per-role overrides, mode
  detection), ``tests/test_litellm_adapter.py`` (mocked
  ``litellm.completion`` covering streaming, usage + cost capture,
  provider inference, auth-failure → friendly error, missing-extra →
  install hint), ``tests/test_grok_native_preserved.py`` (all-Grok
  config still routes to ``run_native_orchestra`` — anti-regression
  for the fast path), ``tests/test_mixed_mode.py`` (mixed-provider
  end-to-end, per-provider cost breakdown, all-adapter run reports
  ``mode_label="adapter"``).

### Added
- **Real web research via Tavily.** A new `sources:` YAML block runs a
  citation-ready research pass *before* the orchestration starts;
  findings are prepended to the goal as a "Web research findings" block
  and the underlying URLs land in `run.citations` so the published
  report carries proper attribution. New module
  `grok_orchestra.sources` exposes `Source`, `Document`, `SearchHit`,
  `FetchedPage`, `ResearchResult` plus a pluggable
  `SearchProvider` registry. Default provider:
  `TavilyProvider` (reads `TAVILY_API_KEY`); `SerpAPIProvider`,
  `BingProvider`, `BraveProvider` ship as skeletons with explicit
  `TODO(prompts-9+)` markers.
- **HTTP fetcher** — `httpx` + `trafilatura` (main-content extraction)
  + `selectolax` (title), with a `ThreadPoolExecutor` for bounded
  concurrency, a 15-second per-page timeout, and a UA string that
  identifies the project + version + repo. Domain allow/blocklists,
  `robots.txt` (fail-open on network errors, fail-closed on explicit
  Disallow), SQLite cache (`$GROK_ORCHESTRA_WORKSPACE/.cache/web/`,
  TTL 1h, stores extracted text + metadata only), and per-run budget
  tracking (default 20 searches / 50 fetches). Over-spend raises a
  `SourceBudgetExceeded` with a clear message.
- **Optional `[js]` extra** (`playwright`, ~300 MB) wires a
  PlaywrightFetcher fallback for sites whose extracted text falls
  below 1000 chars — opt-in per-source via `allow_js: true`.
- **`[search]` extra** — `tavily-python`, `httpx`, `selectolax`,
  `trafilatura`. Required for live web research; simulated mode
  works without it. Added to `dev` so tests run end-to-end (Tavily
  client is mocked; `selectolax` + `trafilatura` exercised for real).
- **New event types** — `web_search_started`,
  `web_search_results`, `fetch_started`, `fetch_completed`. The
  dashboard renders them in a "🌐 web activity" panel above the
  role lanes with hits + fetched titles + cache hits.
- **Run-level telemetry** — `Run` carries `citations` and
  `source_stats` lists; both surface on `/api/runs/{id}` and the run
  detail panel. `source_stats` includes `searches`, `fetches`,
  `cache_hits`, `cache_misses`, and the per-run caps.
- **`weekly-news-digest` template** — bumped to v1.0.0; the
  `requires v0.3+` banner is gone, the YAML now carries a real
  `sources:` block (Tavily, blocklists `pinterest.com` /
  `quora.com`).
- **Tests** — `tests/test_tavily_provider.py` (5 tests, mocked
  Tavily client + registry check), `tests/test_fetcher.py` (5
  tests covering extraction, cache, dedupe, allowlist /
  blocklist), `tests/test_robots.py` (3 tests covering deny / fail-
  open / end-to-end refuses to fetch), `tests/test_budget.py` (4
  tests including thread-safe concurrent spends), and
  `tests/test_web_e2e_simulated.py` (4 tests on the simulated full
  run lifecycle, ws event types, and citations in the published
  Markdown).
- **README "Web research" section** with the YAML reference,
  comparison-table tick, robots / cache / budget defaults, and the
  simulated-mode demo path.

### Added
- **Publisher / report export.** Every run that completes via the
  dashboard now auto-writes a canonical `report.md` plus a
  `run.json` snapshot to
  `$GROK_ORCHESTRA_WORKSPACE/runs/<run-id>/`. The Publisher renders
  three formats from the same source:
  - `report.md` — frontmatter + Executive Summary / Findings /
    Analysis / Stress Test / Synthesis / Lucas Verdict / Citations
    / Appendix sections.
  - `report.pdf` — WeasyPrint render with a cover page, confidence
    gauge, page numbers, header + footer, and print-safe link
    styling.
  - `report.docx` — python-docx render using built-in `Heading 1`
    / `List Number` styles so Word's TOC works.
- **`/api/runs/{id}/report.md|pdf|docx`** endpoints — Markdown is
  cached from the auto-export; PDF + DOCX render lazily in a worker
  thread on first request and cache to disk. Endpoints set
  `Content-Disposition: attachment; filename=report-<run-id>.<ext>`.
- **`grok-orchestra export <run-id> --format=md|pdf|docx|all
  [--output DIR]`** — CLI command that rebuilds reports from the
  persisted `run.json` snapshot. Returns exit `0` and prints the
  written paths (or a JSON payload under `--json`).
- **`[publish]` extra** — `weasyprint`, `pydyf<0.11` (pinned for
  WeasyPrint 62 compatibility), `python-docx`, `markdown`, `pygments`.
  WeasyPrint requires Cairo + Pango on the host; the Docker image
  apt-installs them.
- **`Citation` and `ConfidenceScore` dataclasses** in
  `grok_orchestra/publisher/__init__.py` — Prompts 7 (local docs)
  and 8 (web search) will populate `Citation` directly via a future
  `run.citations` field. The publisher also harvests URLs +
  bracketed-domain refs from Harper's text as a best-effort
  fallback.
- **Frontend updates** — three download buttons (`.md` / `.pdf` /
  `.docx`) appear on the run-results panel after `run_completed`,
  plus a small SVG confidence meter beside the reasoning-token pill
  that animates as soon as Lucas reports.
- **`tests/test_publisher.py`** — 12 tests covering citation
  extraction, Markdown frontmatter / section presence, blocked-verdict
  rendering, DOCX validity (zip + `word/document.xml`), PDF
  presence (skipped when WeasyPrint isn't importable), the
  workspace path resolver, and the full
  `runner → report.md + run.json + /api/.../report.md` round-trip.
- **README "Reports" section** + system-deps install table for
  Cairo/Pango on macOS / Debian / Fedora / Windows. Comparison-
  table list grew with the report format claim.

### Added
- **Docker support.** New multi-stage `Dockerfile` (python:3.11-slim
  builder + slim runtime, venv-copy pattern so the runtime image
  carries no compilers / git), `.dockerignore` to keep the build
  context lean, `docker-compose.yml` for the one-command quickstart
  (`docker compose up --build` → http://localhost:8000), and a
  `docker-compose.dev.yml` overlay that bind-mounts `grok_orchestra/`
  on top of the venv for hot-reload development with
  `uvicorn --reload`. Image runs as a non-root `orchestra` user, ships
  a `/api/health`-based HEALTHCHECK, and is labelled with the OCI
  metadata triple (title / description / source / version / licenses).
- **GHCR publish workflow** — `.github/workflows/docker.yml` builds
  multi-arch (linux/amd64 + linux/arm64) on every push to `main` and
  every `v*.*.*` tag, then pushes to
  `ghcr.io/agentmindcloud/grok-agent-orchestra` with tags `:latest`
  (main only), `:v0.1.0` / `:0.1` (semver tags), `:main`, and
  `:sha-<short>`. Layer cache backed by GitHub Actions' `type=gha`
  backend.
- **Smoke test scripts** — `scripts/docker-smoke-test.sh` (bash) and
  `scripts/docker-smoke-test.ps1` (PowerShell). Build, boot the
  container, poll `/api/health` until 200, tear down. Safe to re-run
  and CI-friendly. Bash version exits non-zero on any failure with
  `set -euo pipefail`; PowerShell version uses
  `$ErrorActionPreference = "Stop"` and a `try/finally` cleanup.
- **`.env.example` expanded** to document every env var the stack
  knows about today (XAI_API_KEY, ORCHESTRA_MODE, LOG_LEVEL) plus
  reserved placeholders for the planned adapter providers
  (OPENAI_API_KEY, ANTHROPIC_API_KEY) and the X deploy target.
- **README "Run in Docker" section** — pre-built `docker pull` from
  ghcr.io, the compose quickstart, the dev overlay command, and a
  pointer to the smoke-test scripts. Comparison table gains a Docker
  row (✅ amd64 + arm64 on ghcr.io).

### Added
- **FastAPI web UI** at `grok-orchestra serve` (new top-level CLI
  command) with WebSocket-streamed multi-agent debates. Install the
  `[web]` extra (`fastapi`, `uvicorn[standard]`, `websockets`,
  `jinja2`, `python-multipart`). HTTP surface:
  `/`, `/api/health`, `/api/templates[?tag=]`,
  `/api/templates/{name}`, `/api/validate`, `/api/dry-run`,
  `/api/run`, `/api/runs[/{id}]`, `/ws/runs/{id}`. State is in-memory
  (last 50 runs); production should swap in Redis/SQLite. Server
  binds to `127.0.0.1` by default; no auth in v1.
- **Single-file HTML dashboard** at
  `grok_orchestra/web/templates/index.html` — Tailwind + CodeMirror
  via CDN, no JS build step. Three-pane layout: template picker /
  YAML editor + Run button / live debate stream with role-coloured
  lanes (Grok=violet, Harper=cyan, Benjamin=amber, Lucas=red). Lucas
  verdict banner + final-output copy-to-clipboard. Mobile-responsive
  (≥ 375px).
- **`event_callback` runtime hook** — `run_orchestra`,
  `run_simulated_orchestra`, `run_native_orchestra`, every pattern,
  and `run_recovery` now accept an optional callback that receives
  every stream event (`MultiAgentEvent` shape) plus synthetic
  lifecycle events (`run_started`, `debate_round_started`,
  `role_started`, `role_completed`, `lucas_started`, `lucas_passed`,
  `lucas_veto`, `pattern_started`, `pattern_phase_started`,
  `run_completed`, `run_failed`). The callback is `None` by default —
  the CLI is byte-for-byte unchanged.
- **`grok_orchestra/_events.py`** — small shared module exposing the
  `EventCallback` type, `event_dict()` factory, and
  `stream_event_to_dict()` helper. Both the CLI runtimes and the web
  layer route through these.
- **`tests/test_event_callback.py`** locks the event-shape contract;
  `tests/test_web_endpoints.py`, `tests/test_simulated_run.py`,
  `tests/test_websocket.py` exercise the full FastAPI stack via
  `TestClient` (synchronous) — every test passes regardless of
  whether `[web]` is installed (skips cleanly otherwise).
- **`templates_json_payload(...)`** in `grok_orchestra/_templates.py` —
  shared helper so the CLI's `_do_list` and the web's `/api/templates`
  cannot drift on field names.

### Changed
- The dispatcher now invokes pattern functions with `event_callback`
  via signature inspection (`inspect.signature`) rather than
  `try/except TypeError`, so a runtime `TypeError` raised during
  orchestration propagates instead of triggering a silent retry.

- **(templates session)** 8 new certified templates + retrofit
  metadata on the existing 10 (description, version, author, tags) so
  every template is filterable. Catalog ships 18 templates total. New:
  `deep-research-hierarchical`, `debate-loop-with-local-docs`
  (requires v0.3+), `competitive-analysis`,
  `due-diligence-investor-memo`, `red-team-the-plan`,
  `weekly-news-digest` (web-search full-fidelity in v0.3+),
  `paper-summarizer`, `product-launch-brief`.
- **(templates session)** `templates` sub-command group —
  `templates list` (with `--tag <tag>` and `--format {table,json}`),
  `templates show <name>`, `templates copy <name> [path]`. Bare
  `templates` defaults to `list`.
- **(templates session)** `dry-run <spec>` top-level shortcut for
  `run --dry-run`. Both `run` and `dry-run` now accept a YAML path or
  the slug of a bundled template.
- **(templates session)** Category grouping in `templates list`,
  shared with the web dashboard's left rail.
- **(templates session)** `tests/test_templates.py` — every shipped
  template parses, validates, and exposes the metadata fields.

### Fixed
- `runtime_simulated.py` and `runtime_native.py` now short-circuit
  `target: stdout` deploys with `console.print(final_content)` +
  `stdout://` sentinel — same fix that landed in `patterns.py` and
  `combined.py` last session, but those two runtimes still had the
  direct `deploy_to_target(final_content, deploy_cfg)` call which
  fails on real Bridge (`unsupported operand type(s) for /:
  'str' and 'str'`). All four call sites are now consistent.

### Fixed
- **Bridge schema strictness** — `load_orchestra_yaml` no longer
  routes Orchestra-only specs through `grok_build_bridge.parser.load_yaml`,
  whose strict `additionalProperties: false` schema rejected
  `goal:` / `orchestra:` / `safety:` / `deploy:` etc. Bridge's
  validator still runs on `combined: true` specs (which carry a real
  `build:` block).
- **`_console.section` signature mismatch** — Orchestra runtimes call
  `section(console, title)` but real Bridge ships `section(title)`.
  Installed a shim in `grok_orchestra/__init__.py` that accepts both.
- **`deploy_to_target` signature mismatch** — Bridge's
  `deploy_to_target(generated_dir, config)` is incompatible with the
  free-text final content Orchestra produces. `target: stdout` now
  short-circuits to `console.print(final_content)` and returns the
  `stdout://` sentinel instead of dispatching to Bridge.

## [0.1.0] - 2026-04-25

First public release. Grok Agent Orchestra turns a single YAML into a Grok
4.20 multi-agent run — either xAI-native (`grok-4.20-multi-agent-0309`) or a
visible prompt-simulated debate between Grok / Harper / Benjamin / Lucas —
with a real safety veto before anything ships.

### Added
- **Parser + schema**. Draft 2020-12 runtime schema at
  `grok_orchestra/schema/orchestra.schema.json` with per-pattern config
  sub-schemas. `load_orchestra_yaml()` delegates Bridge fields to
  `grok_build_bridge.parser.load_yaml`, layers the Orchestra extensions,
  applies defaults, and returns a frozen `MappingProxyType` tree.
  `OrchestraConfigError` carries a `key_path` and renders a Rich panel.
- **Enum / defaults single-source-of-truth** — `OrchestraEnums` and
  `OrchestraDefaults` frozen dataclasses in `parser.py`; schema and
  parser cannot drift.
- **OrchestraClient** — thin `XAIClient` subclass with a streaming
  `stream_multi_agent` method, yields typed `MultiAgentEvent`s, emits a
  `kind="rate_limit"` event on retry-exhausted `RateLimitError`.
- **Native runtime** — `run_native_orchestra` drives the six-phase
  native flow (resolve → stream → audit → veto → deploy → summary)
  inside a live `DebateTUI`.
- **Simulated runtime** — `run_simulated_orchestra` renders a visible
  named-role debate (Grok / Harper / Benjamin / Lucas) with rolling
  transcript compaction, per-role tool routing, and a final Grok
  synthesis turn.
- **DebateTUI** — Rich-`Live` 4-region layout (header / reasoning
  gauge / streamed text / tool-call footer), monochrome cyan/white
  rounded boxes, zero flicker. Re-entrant so the combined runtime can
  wrap phases 2-4 in one continuous show. Degrades gracefully to
  structured log lines on non-TTY stdout.
- **Lucas veto** — `safety_lucas_veto` invokes Lucas at
  `reasoning_effort="high"` on `grok-4.20-0309` with a strict JSON
  output shape; robust parser handles code-fence stripping + regex
  fallback; malformed responses retry with a terser prompt; low
  confidence downgrades to `safe=False`; `print_veto_verdict`
  renders a green approval / red denial panel.
- **Five orchestration patterns** — `hierarchical`, `dynamic-spawn`,
  `debate-loop`, `parallel-tools`, `recovery` — each a composition on
  top of the existing runtimes (<120 LOC each).
  `run_dynamic_spawn` fans out concurrent Harper+Lucas mini-debates
  via `asyncio.gather` over `asyncio.to_thread`. `run_debate_loop`
  iterates with a mid-loop Lucas veto and a structured consensus
  check that exits early.
- **Dispatcher** — `run_orchestra(config, client=None)` resolves
  pattern + mode, looks up the pattern function via `getattr` so
  `unittest.mock.patch` works, and wraps in `run_recovery` when
  `fallback_on_rate_limit.enabled`.
- **Combined Bridge + Orchestra runtime** — `run_combined_bridge_orchestra`
  drives Bridge `generate_code` → `scan_generated_code` → Orchestra
  dispatch (goal augmented with a code summary) → final Lucas veto →
  deploy → summary, all inside one continuous Live panel. `CombinedResult`
  + `BridgeResult` frozen dataclasses.
- **CLI** — `grok-orchestra` Typer app with eight commands: `run`,
  `combined`, `validate`, `templates`, `init`, `debate`, `veto`,
  `version`. Global flags `--no-color`, `--log-level`, `--json`,
  `--version`. Branded violet-accent banner renders once per
  invocation.
- **Exit-code contract** — 0 success / 2 config / 3 runtime /
  4 safety-veto / 5 rate-limit. Every error renders a red Rich panel
  with class, message, and 3-5 "What to try next" bullets.
- **Ten certified templates** + machine-readable `INDEX.yaml` catalog
  covering every pattern and both combined variants.
- **VS Code integration** — Draft-07 user-facing schema with
  `markdownDescription` + `markdownEnumDescriptions` on every field,
  10 YAML snippets, and a package.json patch binding the schema to
  `grok-orchestra.yaml` / `*.orchestra.yaml` / `*.combined.yaml`.
- **Dry-run preview path** — `DryRunOrchestraClient` and
  `DryRunSimulatedClient` replay canned streams keyed on prompt
  shape (role turn / synthesis / classification / consensus / veto)
  so every template + every pattern can be previewed without a live
  xAI call.
- **CI matrix** — lint + test (py3.10/3.11/3.12) + schema-check +
  safety-scan + build + PyPI release on tag. Coverage enforced at
  ≥85%.

### Changed
- **README rewritten as a conversion-grade landing page.** New hero
  block, honest GPT-Researcher comparison table, three-path Quickstart
  (PyPI / GitHub / editable), runnable first-orchestration walkthrough,
  60-second architecture diagram (Mermaid + ASCII fallback), highlighted
  templates, and a thematic roadmap. `docs/images/` placeholder added
  for the TUI demo GIF.

### Build & Release
- **Modernised packaging.** `pyproject.toml` migrated from setuptools to
  Hatchling (PEP 517/621). Dependencies pinned to major-version ranges
  so users do not get stuck on a point release. New `dev`, `web`, and
  `docs` extras (the latter two are placeholders for upcoming work).
- **Dedicated PyPI publish workflow.** `.github/workflows/publish.yml`
  builds wheel + sdist on every `v*.*.*` tag push and publishes via
  PyPI trusted publishing (OIDC). The `release` job has been removed
  from `ci.yml` to avoid double-publishing.
- **Smoke tests for the installed CLI.** `tests/test_cli_smoke.py`
  shells out to the `grok-orchestra` console-script entry point so we
  catch packaging-layer breakage that the in-tree unit tests cannot.
- **Releasing guide.** `docs/RELEASING.md` documents the tag-driven
  publish flow plus a manual `twine` fallback.

### Security
- Lucas veto is enabled by default (`safety.lucas_veto_enabled: true`)
  and fails closed on malformed responses. The combined runtime adds
  a second veto pass on the synthesised content before deploy. See
  [SECURITY.md](SECURITY.md) for the responsible-disclosure policy.

[Unreleased]: https://github.com/agentmindcloud/grok-agent-orchestra/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/agentmindcloud/grok-agent-orchestra/releases/tag/v0.1.0
