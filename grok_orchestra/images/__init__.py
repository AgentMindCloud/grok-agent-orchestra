"""Optional inline image generation for the Publisher.

**Default OFF.** Templates opt in via:

.. code-block:: yaml

    publisher:
      images:
        enabled: true
        provider: flux                 # grok | flux
        budget: 4                      # max images per run
        cover: true
        section_illustrations: 2
        style: "minimal editorial flat illustration, no faces"

Backends
--------
- :class:`GrokImageProvider` — placeholder until xAI ships a stable
  image-generation API. Raises a clear ``NotImplementedError`` with a
  pointer to the Flux fallback.
- :class:`FluxReplicateProvider` — Flux.1 via Replicate (BYOK
  ``REPLICATE_API_TOKEN``). Default backend today.

BYOK contract
-------------
Every backend reads its credential from the environment via the
backend SDK's own resolver. No key ever appears in span attributes,
file paths, or log lines. Refused prompts (real-public-figure names,
deny-list matches) never leave the box.
"""

from __future__ import annotations

from grok_orchestra.images.cache import ImageCache, image_cache_dir
from grok_orchestra.images.factory import resolve_image_provider
from grok_orchestra.images.flux_provider import FluxReplicateProvider
from grok_orchestra.images.grok_provider import GrokImageProvider
from grok_orchestra.images.policy import (
    DEFAULT_STYLE_PREFIX,
    ImagePolicyError,
    apply_style_prefix,
    policy_check,
)
from grok_orchestra.images.types import (
    GeneratedImage,
    ImageBudget,
    ImageBudgetExceeded,
    ImageError,
    ImageProvider,
)

__all__ = [
    "DEFAULT_STYLE_PREFIX",
    "FluxReplicateProvider",
    "GeneratedImage",
    "GrokImageProvider",
    "ImageBudget",
    "ImageBudgetExceeded",
    "ImageCache",
    "ImageError",
    "ImagePolicyError",
    "ImageProvider",
    "apply_style_prefix",
    "image_cache_dir",
    "policy_check",
    "resolve_image_provider",
]
