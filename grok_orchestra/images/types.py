"""Provider-neutral image types + Protocol + budget tracker."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "GeneratedImage",
    "ImageBudget",
    "ImageBudgetExceeded",
    "ImageError",
    "ImageProvider",
]


# --------------------------------------------------------------------------- #
# Errors.
# --------------------------------------------------------------------------- #


class ImageError(RuntimeError):
    """Base for image-layer errors (provider, network, parse)."""


class ImageBudgetExceeded(ImageError):
    """Raised when the per-run image cap is reached."""


# --------------------------------------------------------------------------- #
# GeneratedImage — one rendered image, provider-agnostic.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GeneratedImage:
    """One rendered image. ``data`` is raw PNG bytes."""

    data: bytes
    mime_type: str = "image/png"
    prompt: str = ""
    provider: str = "unknown"
    model: str = "unknown"
    generated_at: str = ""
    cost_usd: float = 0.0
    width: int = 0
    height: int = 0
    cached: bool = False
    cache_key: str = ""

    def public_dict(self) -> dict[str, Any]:
        """Metadata-only dict (no bytes) for span attributes / API responses."""
        return {
            "mime_type": self.mime_type,
            "prompt": self.prompt,
            "provider": self.provider,
            "model": self.model,
            "generated_at": self.generated_at,
            "cost_usd": float(self.cost_usd),
            "width": int(self.width),
            "height": int(self.height),
            "cached": bool(self.cached),
            "cache_key": self.cache_key,
        }


# --------------------------------------------------------------------------- #
# ImageBudget — same shape as the source-layer Budget.
# --------------------------------------------------------------------------- #


@dataclass
class ImageBudget:
    """Mutable per-run cap on image generations."""

    max_images: int = 4
    images: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_cost_usd: float = 0.0
    refusals: int = 0

    _lock: threading.Lock = field(default_factory=threading.Lock)

    def reserve(self, n: int = 1) -> None:
        with self._lock:
            if self.images + n > self.max_images:
                raise ImageBudgetExceeded(
                    f"image budget exceeded: {self.images + n}/{self.max_images}"
                )
            self.images += n

    def hit(self) -> None:
        with self._lock:
            self.cache_hits += 1

    def miss(self) -> None:
        with self._lock:
            self.cache_misses += 1

    def add_cost(self, value: float) -> None:
        with self._lock:
            self.total_cost_usd += float(value)

    def refused(self) -> None:
        with self._lock:
            self.refusals += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "max_images": self.max_images,
                "images": self.images,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "total_cost_usd": round(float(self.total_cost_usd), 6),
                "refusals": self.refusals,
            }


# --------------------------------------------------------------------------- #
# ImageProvider Protocol.
# --------------------------------------------------------------------------- #


@runtime_checkable
class ImageProvider(Protocol):
    """One concrete image backend.

    Implementations are sync to match the rest of the framework. The
    Publisher fans calls out via ``concurrent.futures.ThreadPoolExecutor``
    so multiple providers / multiple images render in parallel.
    """

    name: str
    model: str

    def generate(
        self,
        prompt: str,
        *,
        size: str = "1024x1024",
        n: int = 1,
        style_prefix: str = "",
        **kwargs: Any,
    ) -> Sequence[GeneratedImage]:
        ...
