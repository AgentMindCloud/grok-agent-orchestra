# Marketplace v2 — Orchestra integration

This note describes how Grok Agent Orchestra plugs into the v2
marketplace: the badge system, the `INDEX.yaml` contract, and the
auto-discovery query that lets a visitor say "find me an agent that
does X" and get back a ranked list of Orchestra templates.

## Badge system

Every listing shows at most four pills, in this fixed order:

1. **Pattern badge** — colour-keyed (see `docs/playground.md` for the
   exact colour table).
2. **Mode badge** — `native` / `simulated` / `auto`.
3. **Safety badge** — `🛡 Lucas-certified` when the spec has
   `safety.lucas_veto_enabled: true` (default).
4. **Zero-to-four marketplace badges** — straight from `INDEX.yaml`'s
   `marketplace_badges` array for the template. Examples used by
   the shipped templates:

   - `fast` · `cheap` · `production-ready`
   - `premium` · `rigorous` · `cited`
   - `transparent` · `auditable` · `safety-first`
   - `structured` · `thread-ready`
   - `parallel` · `iterative` · `balanced`
   - `resilient` · `flagship` · `combined` · `ship-ready`

Marketplace runtime enforces:
- At most 4 marketplace badges per listing (earlier badges take
  precedence).
- The safety badge only appears if `safety.lucas_veto_enabled` is
  `true` *and* the template has shipped through the CI schema-check
  (see `.github/workflows/ci.yml`).

## Template source of truth

`grok_orchestra/templates/INDEX.yaml` is the canonical catalog. A
marketplace ingestion job should:

1. Read `INDEX.yaml` (`version: 1`).
2. For each entry, fetch `grok_orchestra/templates/<slug>.yaml`.
3. Call the existing Orchestra validator to ensure the spec still
   validates against the runtime schema (belt-and-braces — CI
   already guarantees this).
4. Index the following fields for search:
   - `name`, `description`, `categories`, `pattern`, `mode`,
     `combined`, `estimated_tokens`, `marketplace_badges`.
   - The body's `goal` string (for full-text match on the prompt).
   - The header comment's `Expected output` line (for snippet
     previews in listing cards).

Changes to `INDEX.yaml` should bump `version:` only on breaking shape
changes (renamed / removed fields). Added fields are backwards-
compatible.

## Auto-discovery — "find me an agent that does X"

A single Grok 4.20 call classifies the user query and ranks the
catalog. The marketplace wraps this call behind a thin search proxy;
the prompt is fixed and version-pinned.

```text
SYSTEM
You are the Grok Agent Orchestra marketplace search assistant. You
match natural-language queries to Orchestra templates. You never
invent templates — you only rank the ones in the provided catalog.

Hard rules:
- Output ONLY valid JSON in this exact shape, no prose, no code fences:
  {
    "matches": [
      {"slug": "<template slug>", "score": <0..1>, "why": "<≤20 words>"}
    ],
    "rationale": "<≤40 words, plain English>"
  }
- Return 1-5 matches ordered by score (highest first).
- Score = how well the template's pattern + mode + categories +
  description fit the query. Heavily penalise combined templates
  when the query does not mention code generation.
- Prefer `orchestra-native-4` when the query is short and general.
- Prefer `orchestra-debate-loop-policy` when the query mentions
  "balanced", "contested", or "policy".
- Prefer `orchestra-hierarchical-research` when the query mentions
  "research", "report", or "two teams".
- Prefer `orchestra-dynamic-spawn-trend-analyzer` when the query
  mentions "parallel", "multi-angle", or "trends".
- Prefer `orchestra-simulated-truthseeker` when the query mentions
  "fact-check", "verify", or "audit".
- Prefer `orchestra-parallel-tools-fact-check` when the query
  mentions per-agent tools or tool scoping.
- Prefer `orchestra-recovery-resilient` when the query mentions
  "reliable", "scheduled", or "production".
- Prefer `orchestra-native-16` when the query mentions "long-form",
  "deep-research", or "weekly".

USER
Query: "<user query here, verbatim>"

Catalog (from INDEX.yaml):
<JSON-serialised list of templates with name, slug, mode, pattern,
combined, description, categories, marketplace_badges>
```

Example input and output:

```
USER
Query: "I need to fact-check a claim from a podcast before I quote it on X"
Catalog: […]
```

```json
{
  "matches": [
    {"slug": "orchestra-simulated-truthseeker", "score": 0.95,
     "why": "Visible 3-round debate tuned for single-claim fact-checks."},
    {"slug": "orchestra-parallel-tools-fact-check", "score": 0.78,
     "why": "Per-agent tool scoping — auditable for safety-adjacent claims."}
  ],
  "rationale": "Query calls for a fact-check with a transparent reasoning chain; truthseeker is the precise fit."
}
```

## Certification workflow

For a community template to earn a marketplace listing:

1. Pass `grok-orchestra validate` against the current schema.
2. Include a header comment block with the same five sections as the
   bundled templates (purpose / env / cost / output / run command).
3. Ship with `safety.lucas_veto_enabled: true`.
4. Pass the CI schema-check + `--dry-run` integration test.
5. Appear in `INDEX.yaml` with at least one category and one badge.

Templates that satisfy all five receive the `🛡 Lucas-certified`
badge. Templates that set `lucas_veto_enabled: false` are marked
`⚠ playground-only` in the listing (no safety badge) and cannot run
from the marketplace's "Try it now" button.
