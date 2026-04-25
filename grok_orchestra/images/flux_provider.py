"""Flux.1 via Replicate — the default image backend (BYOK).

Reads ``REPLICATE_API_TOKEN`` from the environment via the
``replicate`` SDK's own resolver. Returns PNG bytes for each image so
the Publisher can drop them into ``$WORKSPACE/runs/<id>/images/``
verbatim.

Tests mock both ``replicate.run`` and the URL fetch — no live
network call leaves the box in CI.
"""

from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from grok_orchestra.images.policy import apply_style_prefix
from grok_orchestra.images.types import GeneratedImage, ImageError

__all__ = ["FluxReplicateProvider"]

_log = logging.getLogger(__name__)

# Conservative default. ``flux-schnell`` is fast (~3s) and cheap; users can
# pin a different model via constructor kwarg or a future YAML field.
_DEFAULT_MODEL = "black-forest-labs/flux-schnell"

# Flux schnell list price ≈ $0.003 per image — ballpark for the budget panel.
# Real costs come from the Replicate dashboard; this is a UI estimate only.
_BALLPARK_COST_USD = 0.003


class FluxReplicateProvider:
    name = "flux"

    def __init__(
        self,
        *,
        model: str | None = None,
        api_token: str | None = None,
        client: Any | None = None,
        urlopen: Any | None = None,
    ) -> None:
        self.model = model or _DEFAULT_MODEL
        # Test injection points — both replicate's ``run`` and the URL
        # fetcher are swappable so the unit tests don't hit the network.
        self._client = client
        self._urlopen = urlopen or urllib.request.urlopen
        if api_token:
            os.environ.setdefault("REPLICATE_API_TOKEN", api_token)

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not (os.environ.get("REPLICATE_API_TOKEN") or "").strip():
            raise ImageError(
                "FluxReplicateProvider requires REPLICATE_API_TOKEN in the env. "
                "See https://replicate.com/account/api-tokens (BYOK)."
            )
        try:
            import replicate  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover — install hint only
            raise ImageError(
                "Flux image generation requires the [images] extra: "
                "pip install 'grok-agent-orchestra[images]'"
            ) from exc
        self._client = replicate
        return self._client

    def generate(
        self,
        prompt: str,
        *,
        size: str = "1024x1024",
        n: int = 1,
        style_prefix: str = "",
        **kwargs: Any,
    ) -> Sequence[GeneratedImage]:
        client = self._ensure_client()
        full_prompt = apply_style_prefix(prompt, style_prefix)
        width, height = _parse_size(size)
        try:
            output = client.run(
                self.model,
                input={
                    "prompt": full_prompt,
                    "num_outputs": int(n),
                    "aspect_ratio": _aspect_for(width, height),
                    "output_format": "png",
                    **kwargs,
                },
            )
        except Exception as exc:  # noqa: BLE001 — replicate raises lots of shapes
            raise ImageError(f"Flux generation failed: {exc}") from exc

        urls = _normalise_outputs(output)
        if not urls:
            raise ImageError("Flux returned no image URLs")

        out: list[GeneratedImage] = []
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for url in urls[: int(n)]:
            try:
                data = _download(self._urlopen, url)
            except OSError as exc:
                raise ImageError(f"Flux download failed for {url}: {exc}") from exc
            out.append(
                GeneratedImage(
                    data=data,
                    mime_type="image/png",
                    prompt=full_prompt,
                    provider=self.name,
                    model=self.model,
                    generated_at=ts,
                    cost_usd=_BALLPARK_COST_USD,
                    width=width,
                    height=height,
                )
            )
        return out


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def _parse_size(size: str) -> tuple[int, int]:
    try:
        w, h = (int(x) for x in (size or "1024x1024").lower().split("x", 1))
        return w, h
    except (ValueError, TypeError):
        return 1024, 1024


def _aspect_for(w: int, h: int) -> str:
    if w == h:
        return "1:1"
    if w > h:
        return "16:9" if w / max(h, 1) > 1.5 else "4:3"
    return "9:16" if h / max(w, 1) > 1.5 else "3:4"


def _normalise_outputs(output: Any) -> list[str]:
    """Accept whatever shape ``replicate.run`` returns + normalise to URLs.

    Replicate's response is one of:
    - ``str`` (single URL),
    - ``list[str]`` (multiple URLs),
    - ``Iterator[str]`` (streaming),
    - object with ``.url`` (newer SDK shape).
    """
    if output is None:
        return []
    if isinstance(output, str):
        return [output]
    if isinstance(output, (list, tuple)):
        return [_one_url(item) for item in output if _one_url(item)]
    if hasattr(output, "url"):
        return [str(output.url)]
    try:
        # Best-effort iterator drain.
        return [str(x) for x in output if str(x).startswith("http")]
    except TypeError:
        return []


def _one_url(item: Any) -> str:
    if isinstance(item, str):
        return item
    if hasattr(item, "url"):
        return str(item.url)
    return ""


def _download(urlopen: Any, url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "grok-agent-orchestra/images"},
    )
    try:
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
    except urllib.error.URLError as exc:
        raise OSError(f"download error: {exc}") from exc
    if not data:
        raise OSError("empty response body")
    return data
