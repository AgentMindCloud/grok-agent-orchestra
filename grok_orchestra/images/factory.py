"""Resolve an image-provider name → concrete client."""

from __future__ import annotations

from typing import Any

from grok_orchestra.images.types import ImageError, ImageProvider

__all__ = ["PROVIDER_REGISTRY", "register_image_provider", "resolve_image_provider"]


# Lazy-imported to keep the [images] extra optional. Each constructor
# is only loaded when the user picks that provider.
def _flux() -> Any:
    from grok_orchestra.images.flux_provider import FluxReplicateProvider

    return FluxReplicateProvider


def _grok() -> Any:
    from grok_orchestra.images.grok_provider import GrokImageProvider

    return GrokImageProvider


PROVIDER_REGISTRY: dict[str, Any] = {
    "flux": _flux,
    "grok": _grok,
}


def register_image_provider(name: str, factory: Any) -> None:
    """Plug-in hook so users can wire a custom backend at runtime."""
    PROVIDER_REGISTRY[name] = factory


def resolve_image_provider(name: str | None, **kwargs: Any) -> ImageProvider:
    key = (name or "flux").strip().lower()
    factory = PROVIDER_REGISTRY.get(key)
    if factory is None:
        raise ImageError(
            f"unknown image provider {key!r}; registered: {sorted(PROVIDER_REGISTRY)}"
        )
    cls = factory()
    return cls(**kwargs)
