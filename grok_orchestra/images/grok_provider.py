"""Grok image provider — placeholder until xAI ships a stable image API.

xAI hasn't yet exposed a generally-available image-generation endpoint
through the SDK. This file exists so the factory can resolve
``provider: grok`` to a concrete class — and *fail loud* with an
actionable hint pointing at the Flux fallback. It will become a real
implementation the moment the xAI image API is generally available.

Anti-pattern guard: per the prompt's ANTI-PATTERNS section, this
provider must **not** silently no-op. It raises ``NotImplementedError``
with a hint to switch ``--image-provider=flux``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from grok_orchestra.images.types import GeneratedImage, ImageError

__all__ = ["GrokImageProvider"]


class GrokImageProvider:
    name = "grok"
    model = "grok-image-coming-soon"

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
            "Grok image generation is not yet available in the public xAI SDK. "
            "Switch your template to the Flux backend instead:\n"
            "    publisher.images.provider: flux\n"
            "and set REPLICATE_API_TOKEN. See docs/observability.md and the\n"
            "examples/with-images/ template for a worked example."
        )
