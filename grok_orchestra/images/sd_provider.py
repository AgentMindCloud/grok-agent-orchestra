"""Stable Diffusion via Stability AI — skeleton.

TODO(prompts-12+): wire to https://api.stability.ai/v2beta/stable-image/generate.

1. Header ``Authorization: Bearer <STABILITY_API_KEY>``.
2. POST ``prompt`` + ``aspect_ratio`` + ``output_format=png``.
3. Response is the raw PNG body — no extra parse step.
4. Add tests under ``tests/test_image_providers_mock.py`` mirroring
   the Flux mock pattern.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from grok_orchestra.images.types import GeneratedImage, ImageError

__all__ = ["StableDiffusionProvider"]


class StableDiffusionProvider:
    name = "stable_diffusion"
    model = "sd-3.5-large-stub"

    def __init__(self, *, api_key: str | None = None, **_kwargs: Any) -> None:
        del api_key

    def generate(
        self,
        prompt: str,
        *,
        size: str = "1024x1024",
        n: int = 1,
        style_prefix: str = "",
        **kwargs: Any,
    ) -> Sequence[GeneratedImage]:
        del prompt, size, n, style_prefix, kwargs
        raise ImageError(
            "StableDiffusionProvider is a skeleton. Wire up the Stability v2beta "
            "endpoint before use. TODO(prompts-12+) — see "
            "grok_orchestra/images/sd_provider.py"
        )
