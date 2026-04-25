"""Report publisher — turns an orchestration run into a shareable artifact.

The publisher is the *last stage* of every orchestration. It takes the
debate transcript, the four role outputs (Grok / Harper / Benjamin /
Lucas), and the Lucas verdict, and produces three artefacts:

- ``report.md``    — canonical Markdown with YAML frontmatter.
- ``report.pdf``   — WeasyPrint render with a cover page + confidence meter.
- ``report.docx``  — python-docx render with built-in heading styles
                     (Word's TOC works), a verdict table, and footnoted
                     citations.

The Markdown report is the source of truth: PDF and DOCX render from
the same template + extracted citations, so they cannot drift. This
keeps the report stack honest — fix Markdown once, every format
follows.

Lazy imports
------------
``weasyprint``, ``markdown``, ``pygments``, and ``docx`` are part of
the optional ``[publish]`` extras. They're imported inside
``build_pdf`` / ``build_docx`` so the rest of the package keeps
working without them — the Markdown path has zero optional deps.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "Citation",
    "ConfidenceScore",
    "Publisher",
    "PublisherError",
    "extract_role_section",
    "format_citations",
]


# --------------------------------------------------------------------------- #
# Errors.
# --------------------------------------------------------------------------- #


class PublisherError(RuntimeError):
    """Raised when a render fails (typically a missing optional dep)."""


# --------------------------------------------------------------------------- #
# Dataclasses.
# --------------------------------------------------------------------------- #


CitationSourceType = Literal["url", "web", "file", "doc", "search", "internal"]


@dataclass(frozen=True)
class Citation:
    """One citable source extracted (or attached) by an agent.

    ``url`` and ``file_path`` are mutually exclusive in practice but
    both fields exist so a single :class:`Citation` can represent a
    web hit, a local PDF, or a curated document with a stable file
    location. ``used_in_section`` is the slug of the report section
    where the citation was first mentioned (e.g. ``"findings"``).
    """

    source_type: CitationSourceType
    title: str
    url: str | None = None
    file_path: str | None = None
    accessed_at: str | None = None       # ISO-8601 timestamp
    used_in_section: str | None = None
    excerpt: str | None = None           # short verbatim quote, optional

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True)
class ConfidenceScore:
    """Lucas's verdict in publisher-friendly shape.

    ``overall`` is the headline number (0..1). ``per_claim`` maps a
    short claim label to a 0..1 score so the report can show
    per-assertion confidence in a table. ``warnings`` is the list of
    reasons Lucas flagged — non-empty does not necessarily mean
    blocked; the canonical block signal is ``approved=False`` on the
    veto report itself.
    """

    overall: float
    per_claim: Mapping[str, float] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    approved: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": float(self.overall),
            "per_claim": {k: float(v) for k, v in self.per_claim.items()},
            "warnings": list(self.warnings),
            "approved": bool(self.approved),
        }


# --------------------------------------------------------------------------- #
# Run-shape adapter.
#
# The publisher accepts anything dict-like that exposes the fields we need
# (id, yaml_text, final_output, veto_report, events). The web layer's
# `Run` dataclass already matches; the CLI `export` command can build a
# bare dict from the OrchestraResult + persisted artefacts.
# --------------------------------------------------------------------------- #


def _g(run: Any, key: str, default: Any = None) -> Any:
    if isinstance(run, Mapping):
        return run.get(key, default)
    return getattr(run, key, default)


# --------------------------------------------------------------------------- #
# Citation + role-output extraction from the event transcript.
# --------------------------------------------------------------------------- #

_URL_RE = re.compile(r"https?://[^\s)<>\"'\]]+")
_BRACKET_DOMAIN_RE = re.compile(r"\[([a-z0-9.-]+\.[a-z]{2,})\]", re.IGNORECASE)


def extract_role_section(events: Iterable[Mapping[str, Any]], role: str) -> str:
    """Concatenate every ``token`` payload attributed to ``role``.

    Native-mode events lack a ``role`` field — they carry ``agent_id``
    instead, which the web layer maps onto Grok / Harper / Benjamin /
    Lucas at lane 0..3. We honour both.
    """
    role_lower = role.lower()
    agent_id_for_role = {
        "grok": 0,
        "harper": 1,
        "benjamin": 2,
        "lucas": 3,
    }.get(role_lower)

    chunks: list[str] = []
    for ev in events:
        if ev.get("type") != "stream":
            continue
        if ev.get("kind") not in ("token", "final"):
            continue
        ev_role = (ev.get("role") or "").lower()
        if ev_role == role_lower:
            text = ev.get("text") or ""
            if text:
                chunks.append(text)
            continue
        # Native-mode fallback.
        if ev_role == "" and agent_id_for_role is not None:
            if ev.get("agent_id") == agent_id_for_role:
                text = ev.get("text") or ""
                if text:
                    chunks.append(text)
    return "".join(chunks).strip()


def _harvest_citations(text: str, *, section: str) -> list[Citation]:
    """Pull URLs and bracketed-domain refs out of ``text``.

    The publisher does *not* try to fetch metadata or de-duplicate
    against an external corpus — this is best-effort extraction from
    whatever Harper (or another tool-routed agent) wrote. Local-doc
    and live web-search citations will arrive as real ``Citation``
    objects on a future ``run.citations`` field; this function then
    just merges them with the regex-extracted set.
    """
    out: list[Citation] = []
    seen_urls: set[str] = set()
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        out.append(
            Citation(
                source_type="url",
                title=url,
                url=url,
                used_in_section=section,
            )
        )
    seen_domains: set[str] = set()
    for match in _BRACKET_DOMAIN_RE.finditer(text):
        domain = match.group(1).lower()
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        # Only emit a domain-citation if a full URL didn't already cover it.
        if not any(domain in u for u in seen_urls):
            out.append(
                Citation(
                    source_type="search",
                    title=domain,
                    url=f"https://{domain}",
                    used_in_section=section,
                )
            )
    return out


def format_citations(citations: Sequence[Citation]) -> list[dict[str, Any]]:
    """Render citations into a numbered, JSON-serialisable list."""
    return [
        {
            "n": idx + 1,
            **c.to_dict(),
        }
        for idx, c in enumerate(citations)
    ]


# --------------------------------------------------------------------------- #
# Confidence-score extraction from the veto report.
# --------------------------------------------------------------------------- #


def _confidence_from_veto(veto: Mapping[str, Any] | None) -> ConfidenceScore:
    if not veto:
        return ConfidenceScore(overall=0.0, warnings=("no veto report",), approved=False)
    overall = float(veto.get("confidence", 0.0) or 0.0)
    warnings = tuple(str(r) for r in (veto.get("reasons") or []))
    approved = bool(veto.get("approved", True))
    per_claim = veto.get("per_claim") or {}
    if not isinstance(per_claim, Mapping):
        per_claim = {}
    return ConfidenceScore(
        overall=overall,
        per_claim={str(k): float(v) for k, v in per_claim.items()},
        warnings=warnings,
        approved=approved,
    )


# --------------------------------------------------------------------------- #
# Publisher.
# --------------------------------------------------------------------------- #


_TEMPLATES_DIR = Path(__file__).parent / "templates"


class Publisher:
    """Render a run into Markdown, PDF, and DOCX.

    The Markdown render is built off ``default_report.md.j2`` and is
    the single source of truth for both PDF (rendered via WeasyPrint
    after a markdown→HTML pass) and DOCX (rendered via python-docx
    from the same parsed sections).
    """

    def __init__(
        self,
        *,
        template_dir: Path | None = None,
        css_path: Path | None = None,
    ) -> None:
        self.template_dir = template_dir or _TEMPLATES_DIR
        self.css_path = css_path or self.template_dir / "report.css"

    # ------------------------------------------------------------------ #
    # Citation extraction.
    # ------------------------------------------------------------------ #

    def extract_citations(self, run: Any) -> list[Citation]:
        events: list[Mapping[str, Any]] = list(_g(run, "events", []) or [])

        # Pre-attached citations (e.g. from local-docs or web-search
        # adapters in v0.3+) take precedence and keep their metadata.
        attached: list[Citation] = []
        for raw in _g(run, "citations", []) or []:
            if isinstance(raw, Citation):
                attached.append(raw)
            elif isinstance(raw, Mapping):
                attached.append(
                    Citation(
                        source_type=str(raw.get("source_type", "url")),  # type: ignore[arg-type]
                        title=str(raw.get("title", "")),
                        url=raw.get("url"),
                        file_path=raw.get("file_path"),
                        accessed_at=raw.get("accessed_at"),
                        used_in_section=raw.get("used_in_section"),
                        excerpt=raw.get("excerpt"),
                    )
                )

        # Then harvest URLs from the visible role outputs. Harper is
        # the canonical research role; fall back to scanning the
        # final output if Harper produced no events (e.g. native mode).
        harper_text = extract_role_section(events, "Harper")
        scan_pool = harper_text or (_g(run, "final_output") or "")
        attached.extend(_harvest_citations(scan_pool, section="findings"))

        # De-duplicate by (source_type, url|file_path, title).
        seen: set[tuple[str, str, str]] = set()
        deduped: list[Citation] = []
        for c in attached:
            key = (c.source_type, c.url or c.file_path or "", c.title)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(c)
        return deduped

    # ------------------------------------------------------------------ #
    # Markdown.
    # ------------------------------------------------------------------ #

    def build_markdown(self, run: Any) -> str:
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        from grok_orchestra.images_runner import maybe_generate_images
        from grok_orchestra.tracing import get_tracer

        tracer = get_tracer()
        run_id_attr = _g(run, "id") or _g(run, "run_id") or "unknown"
        with tracer.span(
            "publisher/markdown_render",
            kind="markdown_render",
            run_id=run_id_attr,
        ) as span:
            env = Environment(
                loader=FileSystemLoader(str(self.template_dir)),
                autoescape=select_autoescape([]),
                trim_blocks=True,
                lstrip_blocks=True,
            )
            template = env.get_template("default_report.md.j2")
            events = list(_g(run, "events", []) or [])
            veto = _g(run, "veto_report")
            confidence = _confidence_from_veto(veto)
            citations = self.extract_citations(run)
            ctx_pre = {
                "title": _title_for(run),
                "run_id": _g(run, "id") or _g(run, "run_id") or "unknown",
                "template_name": _g(run, "template_name"),
                "version": _g(run, "version", "0.1.0"),
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "duration_seconds": _g(run, "duration_seconds")
                or _duration_from_run(run),
                "executive_summary": _g(run, "final_output") or "",
                "findings": extract_role_section(events, "Harper"),
                "analysis": extract_role_section(events, "Benjamin"),
                "stress_test": extract_role_section(events, "Lucas"),
                "synthesis": extract_role_section(events, "Grok"),
                "confidence": confidence.to_dict(),
                "citations": format_citations(citations),
                "transcript_lines": _human_transcript(events),
            }
            # Optional inline image generation. Default disabled — when
            # the YAML carries `publisher.images.enabled: true` we
            # generate a cover + section illustrations in parallel and
            # surface relative paths the template renders as Markdown
            # image refs.
            image_refs, image_stats = maybe_generate_images(run, ctx_pre)
            if image_stats:
                run_proxy = run if isinstance(run, dict) else None
                if run_proxy is not None:
                    run_proxy.setdefault("image_stats", image_stats)
                else:
                    try:
                        run.image_stats = image_stats
                    except (AttributeError, TypeError):
                        pass
            ctx = {**ctx_pre, "image_refs": image_refs}
            rendered = template.render(**ctx)
            span.set_attribute("output_chars", len(rendered))
            span.set_attribute("citation_count", len(citations))
            span.set_attribute("image_count", len(image_refs))
            return rendered

    # ------------------------------------------------------------------ #
    # PDF.
    # ------------------------------------------------------------------ #

    def build_pdf(self, run: Any, output_path: Path) -> Path:
        try:
            import markdown as _md
            from weasyprint import CSS, HTML
        except ImportError as exc:  # pragma: no cover — checked at runtime
            raise PublisherError(
                "PDF rendering requires the [publish] extra: "
                "pip install 'grok-agent-orchestra[publish]'"
            ) from exc

        from grok_orchestra.tracing import get_tracer

        tracer = get_tracer()
        with tracer.span(
            "publisher/pdf_render",
            kind="pdf_render",
            run_id=_g(run, "id") or _g(run, "run_id") or "unknown",
        ) as span:
            md_text = self.build_markdown(run)
            html_body = _md.markdown(
                _strip_frontmatter(md_text),
                extensions=["fenced_code", "tables", "toc", "sane_lists"],
            )
            full_html = _wrap_html(
                title=_title_for(run),
                run_id=_g(run, "id") or _g(run, "run_id") or "unknown",
                confidence=_confidence_from_veto(_g(run, "veto_report")),
                body=html_body,
            )
            css_text = self.css_path.read_text(encoding="utf-8") if self.css_path.exists() else ""
            output_path.parent.mkdir(parents=True, exist_ok=True)
            # `base_url` lets WeasyPrint resolve the relative
            # ``images/<slug>.png`` refs the Markdown template emits
            # — anchor on the per-run report dir.
            run_id = _g(run, "id") or _g(run, "run_id") or "unknown"
            base_url = str(run_report_dir(str(run_id))) + "/"
            HTML(string=full_html, base_url=base_url).write_pdf(
                target=str(output_path),
                stylesheets=[CSS(string=css_text)] if css_text else None,
            )
            try:
                span.set_attribute("output_bytes", output_path.stat().st_size)
            except OSError:
                pass
            return output_path

    # ------------------------------------------------------------------ #
    # DOCX.
    # ------------------------------------------------------------------ #

    def build_docx(self, run: Any, output_path: Path) -> Path:
        try:
            from grok_orchestra.publisher._docx import write_docx
        except ImportError as exc:  # pragma: no cover
            raise PublisherError(
                "DOCX rendering requires the [publish] extra: "
                "pip install 'grok-agent-orchestra[publish]'"
            ) from exc

        from grok_orchestra.images_runner import maybe_generate_images
        from grok_orchestra.tracing import get_tracer

        tracer = get_tracer()
        run_id = _g(run, "id") or _g(run, "run_id") or "unknown"
        with tracer.span(
            "publisher/docx_render",
            kind="docx_render",
            run_id=run_id,
        ) as span:
            events = list(_g(run, "events", []) or [])
            ctx_pre = {
                "title": _title_for(run),
                "run_id": run_id,
                "template_name": _g(run, "template_name"),
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "executive_summary": _g(run, "final_output") or "",
                "findings": extract_role_section(events, "Harper"),
                "analysis": extract_role_section(events, "Benjamin"),
                "stress_test": extract_role_section(events, "Lucas"),
                "synthesis": extract_role_section(events, "Grok"),
                "confidence": _confidence_from_veto(_g(run, "veto_report")),
                "citations": self.extract_citations(run),
                "transcript_lines": _human_transcript(events),
            }
            # Honour publisher.images. Cached hits make this a no-op on
            # second-write, so it's safe to call from build_docx even
            # though build_markdown will have already triggered it.
            image_refs, _stats = maybe_generate_images(run, ctx_pre)
            ctx = {
                **ctx_pre,
                "image_refs": image_refs,
                "image_dir": str(run_report_dir(str(run_id))),
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            write_docx(ctx, output_path)
            try:
                span.set_attribute("output_bytes", output_path.stat().st_size)
                span.set_attribute("image_count", len(image_refs))
            except OSError:
                pass
            return output_path


# --------------------------------------------------------------------------- #
# Helpers shared by the renderers.
# --------------------------------------------------------------------------- #


def _title_for(run: Any) -> str:
    template_name = _g(run, "template_name") or ""
    if template_name:
        # Pretty-cased title: "orchestra-native-4" → "Orchestra Native 4".
        return template_name.replace("_", "-").replace("-", " ").title()
    return "Grok Agent Orchestra Report"


def _duration_from_run(run: Any) -> float | None:
    started = _g(run, "started_at")
    finished = _g(run, "finished_at")
    if started and finished:
        try:
            return float(finished) - float(started)
        except (TypeError, ValueError):
            return None
    return None


def _human_transcript(events: Iterable[Mapping[str, Any]]) -> list[str]:
    """Flatten the event stream into a Markdown-friendly bullet list."""
    out: list[str] = []
    for ev in events:
        t = ev.get("type")
        role = ev.get("role")
        if t == "stream" and ev.get("kind") == "token":
            text = (ev.get("text") or "").replace("\n", " ").strip()
            if text and len(text) <= 240:
                prefix = f"**{role}**: " if role else ""
                out.append(f"- {prefix}{text}")
        elif t == "role_started":
            out.append(f"- ▸ **{role}** speaking (round {ev.get('round', '?')})")
        elif t == "role_completed":
            out.append(f"- ▾ **{role}** done")
        elif t == "lucas_passed":
            conf = ev.get("confidence")
            out.append(
                f"- ✅ **Lucas** approved (confidence {conf:.2f})"
                if isinstance(conf, (int, float))
                else "- ✅ **Lucas** approved"
            )
        elif t == "lucas_veto":
            out.append(f"- ⛔ **Lucas** vetoed: {ev.get('reason', '')}")
    return out[:200]  # cap so reports don't balloon


def _strip_frontmatter(md: str) -> str:
    """Remove YAML frontmatter so the body renders cleanly to HTML/PDF."""
    if md.startswith("---\n"):
        end = md.find("\n---\n", 4)
        if end != -1:
            return md[end + len("\n---\n") :].lstrip()
    return md


def _wrap_html(*, title: str, run_id: str, confidence: ConfidenceScore, body: str) -> str:
    """Wrap rendered Markdown HTML with our cover page + meta + meter.

    The confidence meter renders as a CSS-driven horizontal gauge —
    avoids WeasyPrint's incomplete SVG-transform support while still
    looking premium.
    """
    pct = max(0.0, min(1.0, confidence.overall))
    pct_int = int(round(pct * 100))
    badge = "approved" if confidence.approved else "blocked"
    badge_class = "ok" if confidence.approved else "fail"
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>{title}</title>
</head><body>
<section class="cover">
  <header class="brand">grok agent orchestra</header>
  <h1>{title}</h1>
  <p class="run-id">run · {run_id}</p>
  <div class="meter" data-confidence="{pct:.2f}">
    <div class="meter-pct">{pct_int}%</div>
    <div class="meter-track">
      <div class="meter-fill meter-fill-{badge_class}"
           style="width: {pct_int}%;"></div>
    </div>
    <div class="meter-label">CONFIDENCE</div>
    <p class="badge badge-{badge_class}">Lucas · {badge}</p>
  </div>
</section>
<main>
{body}
</main>
<footer class="page-footer">{run_id}</footer>
</body></html>"""


def _arc_dasharray(pct: float) -> str:
    # circumference for r=52 → 2πr ≈ 326.726
    circumference = 2 * 3.141592653589793 * 52
    filled = circumference * pct
    return f"{filled:.2f} {circumference - filled:.2f}"


# --------------------------------------------------------------------------- #
# Workspace path resolver — used by the runner and CLI.
# --------------------------------------------------------------------------- #


def workspace_runs_dir() -> Path:
    """Return the directory where per-run report bundles live.

    Honours ``GROK_ORCHESTRA_WORKSPACE`` (set in the Docker image) and
    falls back to ``./workspace`` for local development. Created on
    first call.
    """
    import os

    base = Path(os.environ.get("GROK_ORCHESTRA_WORKSPACE") or "./workspace")
    runs = base / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    return runs


def run_report_dir(run_id: str) -> Path:
    """Per-run report bundle dir (``$WORKSPACE/runs/{run_id}``)."""
    out = workspace_runs_dir() / run_id
    out.mkdir(parents=True, exist_ok=True)
    return out
