"""Glue between the Publisher and ``grok_orchestra.images``.

Lives at the top level (rather than inside ``grok_orchestra/publisher/``)
to keep the publisher's dependency surface lean — the publisher itself
only imports this module *lazily*, so a base install without the
``[images]`` extra never pays for the import.

Public surface
--------------
``maybe_generate_images(run, ctx)`` returns ``(image_refs, stats)``:

- ``image_refs`` — ``{"cover": "images/cover.png", "findings":
  "images/findings.png", ...}``. Empty dict when image gen is
  disabled or every render failed (the report still ships).
- ``stats`` — :meth:`ImageBudget.snapshot` dict surfaced on
  ``Run.image_stats`` for the dashboard's cost panel.

Tracing
-------
Each rendered image gets its own ``image_generation`` span carrying
``provider``, ``model``, ``cache_key``, and ``cost_usd``. The
``SpanKind`` literal already reserves the ``image_generation`` value
(landed in the tracing session for exactly this reason).
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from grok_orchestra.images import (
    DEFAULT_STYLE_PREFIX,
    GeneratedImage,
    ImageBudget,
    ImageBudgetExceeded,
    ImageCache,
    ImageError,
    apply_style_prefix,
    policy_check,
    resolve_image_provider,
)
from grok_orchestra.images.cache import cache_key_for

__all__ = ["build_image_prompt", "maybe_generate_images"]

_log = logging.getLogger(__name__)


_SECTION_HEADINGS: dict[str, str] = {
    "cover": "Report cover",
    "findings": "Research findings",
    "analysis": "Logic & analysis",
    "stress_test": "Stress-test risks",
    "synthesis": "Final synthesis",
}


def maybe_generate_images(
    run: Any,
    ctx: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, Any]]:
    """Generate the cover + section illustrations declared in the YAML.

    Returns ``({slug: relative_path}, stats_dict)``. Image generation
    is best-effort — any single failure logs at WARNING level and the
    report continues without that slug.
    """
    cfg = _images_config(run)
    if not cfg or not cfg.get("enabled"):
        return {}, {}

    provider_name = str(cfg.get("provider") or "flux")
    budget_cap = int(cfg.get("budget", 4) or 0)
    if budget_cap <= 0:
        return {}, {}
    cover = bool(cfg.get("cover", True))
    section_n = int(cfg.get("section_illustrations", 0) or 0)
    style_prefix = str(cfg.get("style") or DEFAULT_STYLE_PREFIX)
    size = str(cfg.get("size") or "1024x1024")
    extra_deny = list(cfg.get("deny_terms") or ())

    out_dir = _run_images_dir(run)
    cache = ImageCache()
    budget = ImageBudget(max_images=budget_cap)

    try:
        provider = resolve_image_provider(provider_name)
    except ImageError as exc:
        _log.warning("image provider %s unavailable: %s", provider_name, exc)
        return {}, {**budget.snapshot(), "error": str(exc)}

    requested: list[tuple[str, str]] = []  # (slug, prompt)
    if cover:
        requested.append(("cover", build_image_prompt("cover", ctx)))
    section_pool = ("findings", "analysis", "stress_test", "synthesis")
    for slug in section_pool[:section_n]:
        requested.append((slug, build_image_prompt(slug, ctx)))
    requested = requested[:budget_cap]

    refs: dict[str, str] = {}
    refs_lock = threading.Lock()

    def _one(slug: str, prompt: str) -> None:
        ok, reason = policy_check(prompt, extra_terms=extra_deny)
        if not ok:
            budget.refused()
            _log.info("image refused for %s: %s", slug, reason)
            return
        try:
            image = _produce(
                provider=provider,
                provider_name=provider_name,
                cache=cache,
                budget=budget,
                prompt=prompt,
                style_prefix=style_prefix,
                size=size,
            )
        except (ImageBudgetExceeded, ImageError) as exc:
            _log.warning("image %s skipped: %s", slug, exc)
            return
        path = _save(image, out_dir, slug=slug)
        with refs_lock:
            refs[slug] = f"images/{path.name}"

    # Render in parallel — the providers are I/O bound. Cap the pool
    # at the budget so we don't waste a thread spinning when budget is 1.
    workers = max(1, min(4, len(requested)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, slug, prompt) for slug, prompt in requested]
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception:  # noqa: BLE001
                _log.warning("image task crashed", exc_info=True)

    return refs, budget.snapshot()


# --------------------------------------------------------------------------- #
# Internals.
# --------------------------------------------------------------------------- #


def _produce(
    *,
    provider: Any,
    provider_name: str,
    cache: ImageCache,
    budget: ImageBudget,
    prompt: str,
    style_prefix: str,
    size: str,
) -> GeneratedImage:
    from grok_orchestra.tracing import get_tracer

    tracer = get_tracer()
    full_prompt = apply_style_prefix(prompt, style_prefix)
    key = cache_key_for(
        provider=provider_name,
        model=getattr(provider, "model", "unknown"),
        prompt=full_prompt,
        style_prefix=style_prefix,
        size=size,
    )

    with tracer.span(
        f"image_generation/{provider_name}",
        kind="image_generation",
        provider=provider_name,
        model=getattr(provider, "model", "unknown"),
        prompt=full_prompt,
        size=size,
        cache_key=key,
    ) as span:
        cached = cache.get(key)
        if cached is not None:
            budget.hit()
            span.set_attribute("cached", True)
            return cached

        budget.miss()
        budget.reserve(1)
        results: Sequence[GeneratedImage] = provider.generate(
            prompt,
            size=size,
            n=1,
            style_prefix=style_prefix,
        )
        if not results:
            raise ImageError(f"{provider_name} returned no images")
        image = results[0]
        # Backfill metadata before caching so the cached record is
        # complete (some providers don't set every field).
        image = GeneratedImage(
            data=image.data,
            mime_type=image.mime_type or "image/png",
            prompt=full_prompt,
            provider=provider_name,
            model=image.model or getattr(provider, "model", "unknown"),
            generated_at=image.generated_at
            or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            cost_usd=float(image.cost_usd or 0.0),
            width=int(image.width or 1024),
            height=int(image.height or 1024),
            cached=False,
            cache_key=key,
        )
        budget.add_cost(image.cost_usd)
        try:
            cache.put(key, image)
        except OSError as exc:
            _log.warning("image cache write failed: %s", exc)
        span.set_attribute("cost_usd", float(image.cost_usd))
        span.set_attribute("bytes", len(image.data))
        return image


def _save(image: GeneratedImage, out_dir: Path, *, slug: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-z0-9_-]+", "-", slug.lower()).strip("-") or "image"
    path = out_dir / f"{safe}.png"
    # Resample to ≤ 1024 on the longest side so PDFs stay slim.
    data = _maybe_resample(image.data)
    path.write_bytes(data)
    return path


def _maybe_resample(data: bytes, *, max_dim: int = 1024) -> bytes:
    """Return ``data`` shrunk to ``max_dim`` on the longest side. Pillow-only.

    Falls through unchanged when Pillow isn't installed — the [images]
    extra always pulls it in, but the publisher must keep working with
    only an external image source if a future user wires one.
    """
    try:
        import io as _io

        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        return data
    try:
        with Image.open(_io.BytesIO(data)) as img:
            if max(img.size) <= max_dim:
                return data
            img.thumbnail((max_dim, max_dim))
            buf = _io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
    except Exception:  # noqa: BLE001 — never crash a report on resample
        return data


def _images_config(run: Any) -> Mapping[str, Any] | None:
    """Resolve ``publisher.images`` from the run's YAML.

    Re-parses ``run.yaml_text`` (cheap; the YAML is small) so the
    Publisher doesn't need a back-channel into the runner's parsed
    config.
    """
    yaml_text: str | None = None
    if isinstance(run, Mapping):
        yaml_text = run.get("yaml_text")
        # Allow tests to inject a parsed config directly.
        injected = run.get("publisher")
        if isinstance(injected, Mapping):
            return injected.get("images") if "images" in injected else injected
    else:
        yaml_text = getattr(run, "yaml_text", None)
        injected = getattr(run, "publisher", None)
        if isinstance(injected, Mapping):
            return injected.get("images") if "images" in injected else injected
    if not yaml_text:
        return None
    try:
        import yaml

        loaded = yaml.safe_load(yaml_text) or {}
    except Exception:  # noqa: BLE001
        return None
    publisher = (loaded or {}).get("publisher") or {}
    images = publisher.get("images") if isinstance(publisher, Mapping) else None
    return images if isinstance(images, Mapping) else None


def _run_images_dir(run: Any) -> Path:
    from grok_orchestra.publisher import run_report_dir

    run_id = (
        (run.get("id") if isinstance(run, Mapping) else getattr(run, "id", None))
        or "unknown"
    )
    return run_report_dir(str(run_id)) / "images"


def build_image_prompt(slug: str, ctx: Mapping[str, Any]) -> str:
    """Deterministic prompt generator per slug.

    The prompt is intentionally short + abstract so the policy layer
    keeps refusal rates low. Operators who want LLM-authored prompts
    can swap this function for a small LLM-call helper.
    """
    title = str(ctx.get("title") or "Grok Agent Orchestra report")
    if slug == "cover":
        summary = str(ctx.get("executive_summary") or "")[:200]
        topic = title.lower()
        return (
            f"Cover image for a research report titled '{title}'. "
            f"Theme: {topic}. {summary}"
        ).strip()
    body = str(ctx.get(slug) or "").split("\n\n", 1)[0][:240]
    heading = _SECTION_HEADINGS.get(slug, slug.replace("_", " ").title())
    return (
        f"Section illustration for '{heading}' inside a report titled '{title}'. "
        f"Theme: {body}"
    ).strip()
