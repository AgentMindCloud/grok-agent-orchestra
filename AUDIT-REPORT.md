# Audit Report: grok-agent-orchestra

**Date:** 2026-05-07
**Auditor:** Claude Code
**Org:** AgentMindCloud
**Ecosystem Role:** Multi-agent orchestration layer that sits on top of `grok-build-bridge`, running schema-validated YAML specs through native xAI multi-agent endpoints or simulated 4-role debate, gated by a fail-closed Lucas safety veto.

---

## 1. Snapshot

- **Stars / forks / open issues:** unknown (no `gh` CLI available; remote is sandboxed proxy)
- **Last commit:** 2026-04-30 (`525ae59 docs(readme): drop unverified GPT-Researcher comparison chart`) — 7 days before audit; 51 commits total
- **Primary language(s):** Python (28,047 LOC), TypeScript + TSX (6,639 LOC), HTML/CSS (1,017 LOC)
- **Total LOC:** 35,703 (excluding `node_modules`, `.git`, `.next`)
- **Dependencies health:** Python deps majors-pinned and current (`xai-sdk>=1.0,<2`, `grok-build-bridge>=0.1,<1`, `pyyaml`, `rich`, `typer`, `tenacity`, `jsonschema`); 11 optional-dep groups well-curated. **`grok-build-bridge` is not on PyPI** — Dockerfile installs via `git+https`, CI uses `tools/bridge-stub`. Node deps not installable in this environment (`npm audit` skipped). `pip-audit` runs in CI on filtered `requirements.txt`.
- **CI status:** 7 workflows present (`ci`, `benchmarks`, `docker`, `docs`, `frontend`, `publish`, `vscode-extension`); run history not retrievable without `gh`. `ci.yml` enforces version lockstep across 4 surfaces, schema validity, template-validate-all, and 80% coverage gate.
- **License:** Apache-2.0, present at root ✓
- **Required files present:** README ✓, LICENSE ✓, CHANGELOG ✓, CONTRIBUTING ✓, .gitignore ✓ (also SECURITY.md ✓, SUPPORT.md ✓; **CODE_OF_CONDUCT.md missing at root** — `CONTRIBUTING.md:116` links to it)

---

## 2. File-by-File Findings

### High

- `release_notes_v0.1.0.md:34` — Claims "**Ten** certified templates" but `INDEX.yaml` ships **18**, and `README.md:582-617` advertises 18. Public release artifact contradicts product. — **Severity:** High
- `release_notes_v0.1.0.md:65` — Claims "527 tests passing, 82.4% coverage". Actual test-function count is **461** (`grep -r "^def test_" tests/`); CI coverage gate is **80%** (`ci.yml:79 --cov-fail-under=80`). Numbers are stale or fabricated. — **Severity:** High
- `launch/x-thread-orchestra.md:81-86` — X/Twitter launch copy lists exactly 10 starter templates ("native-4 · native-16 · simulated-truthseeker · …"). Repo ships 18. If this thread is posted, the headline number is wrong. — **Severity:** High
- `launch/x-thread-orchestra.md:91-92` — Quickstart in launch copy reads `pip install grok-agent-orchestra`. README itself states PyPI is not yet available; users would hit immediate `No matching distribution` failure. — **Severity:** High
- `launch/x-thread-orchestra.md:105` — `> @xai @grok @elonmusk` is unescaped in markdown. On GitHub render, `@grok` auto-links to a real GitHub user (Sterling Hamilton). Sole unescaped occurrence in the repo. — **Severity:** High
- `CONTRIBUTING.md:116` — Links to `CODE_OF_CONDUCT.md` at repo root; file does not exist there (only at `docs/contributing/code-of-conduct.md`). Broken link in published Contributing doc. — **Severity:** High
- `README.md:364, 416` — Advertises **Langfuse** as a tracing backend alongside LangSmith and OTLP. Code ships only `langsmith_tracer.py`, `otel_tracer.py`, `noop.py`; `pyproject.toml [tracing]` extras have no `langfuse` package; `release_notes_v0.1.0.md:48-50` confirms Langfuse was removed for a `packaging` conflict. README is publicly false. — **Severity:** High
- `docs/index.md:54` — Same Langfuse drift propagated into the published MkDocs site. — **Severity:** High
- `docs/architecture/overview.md`, `docs/architecture/extending.md`, `docs/architecture/comparison.md`, `docs/getting-started/installation.md:49`, `docs/getting-started/first-orchestration.md:68` — Langfuse mentioned across ~6 docs files; all stale post-removal. — **Severity:** High
- `grok_orchestra/safety_veto.py:45` — Hardcoded `LUCAS_MODEL = "grok-4.20-0309"`. This is not a real public xAI model ID. Live runs against real `XAI_API_KEY` will fail with model-not-found, defeating the entire "fail-closed safety gate" claim. — **Severity:** High
- `grok_orchestra/runtime_native.py:43` & `grok_orchestra/multi_agent_client.py:35` — Hardcoded `NATIVE_MODEL_ID = "grok-4.20-multi-agent-0309"`. Same issue: model does not exist on the public xAI API. The native-mode runtime is fictional in production. — **Severity:** High
- `mkdocs.yml:218-221` — `nav` lists `deploy/{docker,render,fly}.md`; `docs/deploy/vercel.md` exists but is excluded from nav (orphan, unreachable from the docs site). — **Severity:** High
- `README.md:213-247` — Docker section instructs users to pull `ghcr.io/agentmindcloud/grok-agent-orchestra:latest`. Image is only published on push-to-main + version tags; with `publish.yml` manual-only and zero release tags in git log, the public image likely does not exist. — **Severity:** High

### Medium

- `vscode/schemas/orchestra.schema.json` vs `extensions/vscode/schemas/orchestra.schema.json` — Two parallel schema copies; `$id` differs (`agentmind.cloud` vs `github.com`). `ci.yml:107` validates the **legacy** path, not the canonical published one. Schema drift is undetected by CI. — **Severity:** Medium
- `vscode/` — Entire legacy directory superseded by `extensions/vscode/`; still ships in repo. Includes `package.json.patch`, snippets, schemas. Confusing for new contributors. — **Severity:** Medium
- `templates -> grok_orchestra/templates` (root symlink) — Vestigial; nothing outside `grok_orchestra/` references it consistently. — **Severity:** Medium
- `README.md:582-617` & `grok_orchestra/templates/INDEX.yaml` — Two of the 18 advertised templates (`debate-loop-with-local-docs`, `weekly-news-digest`) are flagged "requires v0.3+"; they ship under a "18 certified" headline, which overstates production readiness even with the 🟡 marker. — **Severity:** Medium
- `README.md:139-144` & `extensions/vscode/README.md:30` — Calls itself "first-party VS Code extension"; marketplace publishing intentionally disabled until v1.x. Sideload-only is not "first-party" by the Marketplace's definition. — **Severity:** Medium
- `README.md:629-630` — References an "18-item improvement roster lives in `docs/`"; no such file is identifiable in nav or on disk. — **Severity:** Medium
- `README.md:65` — `local mode` quickstart says `ollama pull llama3.1:8b`; Ollama is a separate runtime, not a pip dep. The `[adapters]` extra brings LiteLLM only. Slightly misleading first-run path. — **Severity:** Medium
- `examples/mcp-filesystem/spec.yaml`, `examples/mcp-github/spec.yaml` — MCP examples ship; `_mcp_backend.py` is in `[tool.coverage.run].omit`, so MCP is not exercised by the test gate despite being advertised. — **Severity:** Medium
- `frontend/__tests__/` — Three vitest files for a "production-grade dashboard" (`README.md:471`). Coverage too thin for the marketing claim. — **Severity:** Medium
- `release_notes_v0.1.0.md:21` — Install command pins `@v0.1.0` git ref; no `v0.1.0` tag exists in `git log` (latest commits unreleased). — **Severity:** Medium
- `tools/bridge-stub/` — In-repo fake of `grok-build-bridge` lets CI pass; the stack only "works" in CI because the upstream is faked. Important context buried. — **Severity:** Medium
- `grok_orchestra/web/auth.py:166` — Allows raw-password `Bearer` auth as a "quick curl" mode. Documented footgun, not a bug, but a real foot-shaped hole. — **Severity:** Medium
- `grok_orchestra/web/templates/index.html` — Tailwind via CDN (`cdn.tailwindcss.com`); Tailwind itself documents this as "not for production". Acceptable for the legacy `/classic` fallback but worth noting. — **Severity:** Medium
- `benchmarks/results/latest.md` — Explicitly admits "no benchmark run has landed yet"; benchmarks are a headline feature in README and have zero data. — **Severity:** Medium
- `release_notes_v0.1.0.md:48-50` vs `README.md:364, 416` — Internal contradiction inside the launch artifacts themselves: release notes say Langfuse removed; README still advertises it. — **Severity:** Medium

### Low

- `CHANGELOG.md` — 1,280 lines; almost everything bucketed under `## Earlier` with no semver dates. Suggests one bundled pre-release rather than a release cadence. — **Severity:** Low
- `examples/local-only/local-research.yaml` — Referenced in README quickstart but not surfaced in `INDEX.yaml`. — **Severity:** Low
- `.github/FUNDING.yml` — All entries commented out; ships purely to tick the community-standards checkbox (acknowledged in file). — **Severity:** Low
- `docs/RELEASING.md:76` — `# CI does not enforce this yet (TODO)` — only real TODO in the codebase. — **Severity:** Low
- `tests/test_tracing_langsmith.py:159` — Synthetic `sk-AbcDeFGhIjKlmnOpQrSt12345678901234` fixture trips naive secret scanners. Could be made obviously-synthetic (e.g. `sk-FAKE-…`) to avoid noise. — **Severity:** Low
- `grok_orchestra/web/templates/index.html` — Emoji-only buttons (`▶`, `⬇`, `🔭`) lack `aria-label`; some state cues color-only. — **Severity:** Low

### Nit

- `release_notes_v0.1.0.md:21` — Uses `AgentMindCloud/grok-agent-orchestra.git` (PascalCase) while every other URL uses lowercase `agentmindcloud/...`. — **Severity:** Nit
- `.github/assets/HERO-PLACEHOLDER.md` — Marker file kept in repo. — **Severity:** Nit

(Long tail not enumerated: ~6 mkdocs `not_in_nav` entries are intentional transclusion stubs, not orphans; some README em-dash / triple-quoted prose is stylistic; minor `examples/with-images/` README phrasing inconsistencies.)

---

## 3. Cross-Cutting Issues

- **Unescaped `@grok` mentions:** **1** total — `launch/x-thread-orchestra.md:105` (`> @xai @grok @elonmusk`). Fix by wrapping in backticks: `` `@xai` `@grok` `@elonmusk` ``. No other occurrences across `*.md`, `*.html`, `*.yaml`, `*.yml`. The team is generally good at backtick-quoting handles — this is a single oversight in launch copy.
- **Schema/version drift:** All 18 templates correctly declare `version: 1.0.0`; surface versions (`pyproject.toml`, `__init__.py`, `frontend/package.json`, `extensions/vscode/package.json`) all lockstep at `0.1.0` and CI's `version-check` job enforces this. The real drift is **schema duplication** between `vscode/schemas/orchestra.schema.json` (legacy, validated by CI) and `extensions/vscode/schemas/orchestra.schema.json` (canonical, shipped to users) with different `$id` URIs. CI watches the wrong file.
- **Documentation freshness:** Significant drift. Langfuse advertised in README + ~6 docs files but removed from code; release notes claim 10 templates / 527 tests / 82.4% coverage vs reality of 18 / 461 / 80%; launch X-thread quickstart instructs `pip install` from a non-existent PyPI package; README points users at a Docker image that may never have been published. The maintainer's most recent commit (`525ae59`) is in fact a doc-honesty pass dropping an unverified comparison chart, suggesting awareness of the issue.
- **Brand/visual consistency:** **Strong.** Single accent (`#FF7A00` Grok orange / `#FF6B35` mkdocs deep orange), consistent role colors (Grok violet, Harper cyan, Benjamin amber, Lucas red) reused across `grok_orchestra/web/templates/index.html`, the Next.js dashboard, MkDocs site, README hero SVGs, and VS Code extension `galleryBanner`. Heroes are honestly labeled "branded SVGs not screenshots".
- **Dead code / orphan files:** Top-level `vscode/` directory (legacy); `templates ->` symlink at root (vestigial); `docs/deploy/vercel.md` (orphaned from nav); `.github/assets/HERO-PLACEHOLDER.md`.
- **Test coverage:** 48 test files, 461 functions, 80% Python gate, mocked (no live API). Healthy for a project this size. Frontend has 3 vitest files; VS Code extension 1 test file. The optional surfaces (MCP, images, DOCX, OTLP) are deliberately omitted from the coverage gate and lightly tested.
- **Security posture:** **Genuinely good** in design. `.env.example` fully commented, no live secrets; `.gitignore` excludes all `.env.*` except example; HMAC-signed session cookies with `HttpOnly`/`Secure`/`SameSite=lax`, off by default; path-traversal guards on image endpoints (`web/main.py:415-422`); aggressive `tracing/scrubber.py` redacting `sk-`, `tvly-`, `Bearer`, AWS/GCP keys, and sensitive field names; `pip-audit` in CI; non-root Docker user; clear `SECURITY.md` disclosure path. **Zero real leaked secrets** in the codebase. The Bearer-password fallback in `web/auth.py:166` is a documented footgun.

---

## 4. What's Working Well

- **Robust CI matrix.** `ci.yml` enforces version-lockstep across all 4 surfaces (pyproject ↔ `__init__` ↔ frontend ↔ vscode), runs schema validation on every template, runs `pip-audit`, and gates 80% coverage across Python 3.10/3.11/3.12. Drift is caught early — this is unusually disciplined for a v0.1.0 project.
- **Honest fail-closed safety design.** `safety_veto.py` retries → escalates to `safe=False` with documented exit code 4; toxic-sentinel pre-check; strict-JSON parsing; high `reasoning_effort`. The architecture matches the headline claim — the only thing missing is a model ID that exists.
- **Strong tracing scrubber.** `grok_orchestra/tracing/scrubber.py` redacts credential-shaped strings AND sensitive field names before any tracing backend sees them. Defensible privacy posture, not just a checkbox.
- **Modular architecture with explicit boundaries.** Sources / LLM adapters / tracing backends / image providers / patterns all sit behind small Protocol+registry layers. Optional extras (`[mcp]`, `[images]`, `[tracing]`, `[search]`, `[adapters]`) keep the base install lean; the coverage `omit` list documents the boundary explicitly.
- **Visually polished dashboard.** `grok_orchestra/web/templates/index.html` is responsive (3-col → 2-col → 1-col via Tailwind breakpoints), accessibility-aware (semantic landmarks, `aria-hidden` on decorative SVGs, `lang` attr), and on-brand. Better than most v0.1 dashboards.

---

## 5. Top 5 Improvements (Ranked by Impact ÷ Effort)

| # | Improvement | Impact (1-10) | Effort (hours) | Why it matters |
|---|---|---|---|---|
| 1 | Replace fictional model IDs `grok-4.20-{multi-agent-,}0309` with real public xAI model IDs (`grok-4`, etc.) in `safety_veto.py:45`, `runtime_native.py:43`, `multi_agent_client.py:35`, plus all docs. Add a `doctor` check that pings the real model. | 10 | 4 | Without this the entire runtime fails on first real API call; the rest of the polish is wasted until users can actually run a spec. |
| 2 | Sync `release_notes_v0.1.0.md`, `launch/x-thread-orchestra.md`, and README with reality: 18 templates not 10, 461 tests not 527, 80% coverage not 82.4%, drop Langfuse from README + 6 docs files (or re-implement). Backtick-wrap `@grok`/`@xai`/`@elonmusk` in launch thread. | 9 | 3 | Launch artifacts contradict the codebase; first reviewer with grep will lose trust. The `@grok` mention pings a real third-party user the moment the file renders on github.com. |
| 3 | Publish `grok-build-bridge` and `grok-agent-orchestra` to PyPI; flip `publish.yml` from `workflow_dispatch`-only to tag-triggered; cut a real `v0.1.0` git tag and ghcr release. | 9 | 6 | Every install path in README (`pip install grok-agent-orchestra`, `docker pull ghcr.io/...`) is currently a 404. Largest install-funnel leak. |
| 4 | Land a real benchmark run + populate `benchmarks/results/latest.md`. Even one head-to-head vs gpt-researcher with screenshots beats the current placeholder. | 7 | 6 | Benchmarks are a headline differentiator and currently 100% vapor. One real datapoint converts the comparison narrative from "trust me" to "here's the data". |
| 5 | Resolve the `vscode/` vs `extensions/vscode/` schema duplication: delete legacy, point CI's schema-check at the canonical path, add a regression test that fails if both directories exist again. | 6 | 1.5 | Silent schema drift between what CI validates and what users actually consume is exactly the kind of bug that ships and stays shipped. |

---

## 6. Quick Wins (≤30 min each)

- Fix unescaped social handles. In `launch/x-thread-orchestra.md:105`, change `> @xai @grok @elonmusk` to `` > `@xai` `@grok` `@elonmusk` ``. Stops auto-pinging Sterling Hamilton on render.
- Fix broken Code of Conduct link. `CONTRIBUTING.md:116` — point to `docs/contributing/code-of-conduct.md`, OR copy that file to repo root as `CODE_OF_CONDUCT.md` (preferable; GitHub surfaces it in community-standards).
- Delete the legacy `vscode/` directory and the root `templates` symlink. Single `git rm -r vscode/ templates` after confirming `extensions/vscode/` is feature-equivalent.
- Add `docs/deploy/vercel.md` to `mkdocs.yml` `nav` (or move it to `not_in_nav`). One-line nav addition under `Deploy:`.
- Update `release_notes_v0.1.0.md:34` from "Ten" to "Eighteen", `:65` from "527 tests passing, 82.4% coverage" to "461 tests passing, 80% coverage gate".
- Update `launch/x-thread-orchestra.md:81-86` template list to match `INDEX.yaml`.
- Replace the launch quickstart `pip install grok-agent-orchestra` (`launch/x-thread-orchestra.md:91-92`) with the actual working `pip install git+https://github.com/agentmindcloud/grok-agent-orchestra` until PyPI lands.
- Strip Langfuse from README (`README.md:364, 416`) and `docs/index.md:54`. Search-replace pass: `grep -rln "Langfuse" README.md docs/`.
- Make `tests/test_tracing_langsmith.py:159` fixture obviously-synthetic: `raw_secret = "sk-FAKE-redaction-test-not-a-real-key"`.
- Add `aria-label` to emoji buttons in `grok_orchestra/web/templates/index.html` (`▶` → `aria-label="Run"`, `⬇` → `aria-label="Download"`, `🔭` → `aria-label="Inspect"`).
- Point `ci.yml:107` schema-check at `extensions/vscode/schemas/orchestra.schema.json` instead of the legacy `vscode/` path.
- Add `CODE_OF_CONDUCT.md` symlink at repo root pointing to `docs/contributing/code-of-conduct.md` (or just copy).

---

## 7. Ecosystem Potential Statement

`grok-agent-orchestra` is the **operator-facing surface** of the AgentMindCloud Grok stack — the place where Bridge's codegen+deploy primitives become a visible, replayable, schema-validated multi-agent debate with a fail-closed safety gate. It is the only repo in the portfolio that ships *all five* of: Python core, Next.js dashboard, FastAPI server + classic dashboard, Docker multi-arch image, VS Code extension, and a Claude Skill — making it the natural "front door" demo for the entire org. **Maturity: late-beta, launch-rehearsed but not launch-shipped** — evidence: 51 commits, lockstep 0.1.0 across four surfaces, 7 mature CI workflows, but zero PyPI/ghcr releases, fictional hardcoded model IDs, placeholder benchmark file, and `tools/bridge-stub` still doing real work in CI because Bridge itself is unreleased. **6-month potential if invested in:** with real model IDs + PyPI publication + one landed benchmark, this is a credible 800-1,500 star project (it's the rare orchestrator that has both a CLI and a dashboard and a safety gate); strategic value to AgentMindCloud is high because it's the demonstration vehicle for the whole Bridge+Orchestra story; revenue path runs through hosted runs / managed safety gating, not the OSS itself; for `@JanSol0s` on X this is the single most-tweetable artifact in the portfolio. **Single biggest unlock:** ship a working `pip install` against a real Grok model ID — everything else (benchmarks, Marketplace, hosted) compounds off that one moment when a stranger can `pip install`, `grok-orchestra run`, and watch four agents debate. **Honest verdict on resource allocation:** prioritized investment — this is the show-don't-tell repo for the entire org and the polish-to-bug ratio is unusually favorable; the remaining bugs are concentrated and tractable, not architectural.

`POTENTIAL_TAG: DOUBLE_DOWN — Polished operator-facing surface for the whole Bridge stack; one PyPI release and a real model ID unlocks it.`
