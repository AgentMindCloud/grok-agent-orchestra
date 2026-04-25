"""On-disk image cache keyed on (provider, model, prompt, style, size).

Cache files live at::

    $GROK_ORCHESTRA_WORKSPACE/.cache/images/<sha256>.png
    $GROK_ORCHESTRA_WORKSPACE/.cache/images/<sha256>.json   # metadata

A cache hit returns a :class:`GeneratedImage` with ``cached=True`` and
``cost_usd=0.0`` so the budget tracker can treat it correctly.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from grok_orchestra.images.types import GeneratedImage

__all__ = ["ImageCache", "cache_key_for", "image_cache_dir"]


def image_cache_dir() -> Path:
    base = Path(os.environ.get("GROK_ORCHESTRA_WORKSPACE") or "./workspace")
    out = base / ".cache" / "images"
    out.mkdir(parents=True, exist_ok=True)
    return out


def cache_key_for(
    *,
    provider: str,
    model: str,
    prompt: str,
    style_prefix: str,
    size: str,
) -> str:
    payload = "\x1f".join(
        [
            provider.strip().lower(),
            model.strip().lower(),
            (prompt or "").strip(),
            (style_prefix or "").strip(),
            (size or "").strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ImageCache:
    """File-system cache. Single-writer per process via a small lock."""

    def __init__(self, *, path: Path | None = None) -> None:
        self.path = Path(path) if path else image_cache_dir()
        self.path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def get(self, key: str) -> GeneratedImage | None:
        png = self.path / f"{key}.png"
        meta = self.path / f"{key}.json"
        if not png.exists() or not meta.exists():
            return None
        with self._lock:
            try:
                metadata = json.loads(meta.read_text(encoding="utf-8"))
                data = png.read_bytes()
            except (OSError, json.JSONDecodeError):
                return None
        return GeneratedImage(
            data=data,
            mime_type=str(metadata.get("mime_type", "image/png")),
            prompt=str(metadata.get("prompt", "")),
            provider=str(metadata.get("provider", "")),
            model=str(metadata.get("model", "")),
            generated_at=str(metadata.get("generated_at", "")),
            cost_usd=0.0,
            width=int(metadata.get("width", 0)),
            height=int(metadata.get("height", 0)),
            cached=True,
            cache_key=key,
        )

    def put(self, key: str, image: GeneratedImage) -> Path:
        png = self.path / f"{key}.png"
        meta = self.path / f"{key}.json"
        with self._lock:
            png.write_bytes(image.data)
            meta.write_text(
                json.dumps(
                    {
                        "mime_type": image.mime_type,
                        "prompt": image.prompt,
                        "provider": image.provider,
                        "model": image.model,
                        "generated_at": image.generated_at
                        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "width": image.width,
                        "height": image.height,
                        "cost_usd": float(image.cost_usd),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        return png

    def clear(self) -> None:
        with self._lock:
            for child in self.path.iterdir():
                if child.is_file():
                    child.unlink(missing_ok=True)
