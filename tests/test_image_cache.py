"""On-disk image cache: deterministic key, hit semantics."""

from __future__ import annotations

from pathlib import Path

import pytest

from grok_orchestra.images import GeneratedImage, ImageCache
from grok_orchestra.images.cache import cache_key_for


def _img(data: bytes = b"png-bytes-here") -> GeneratedImage:
    return GeneratedImage(
        data=data,
        mime_type="image/png",
        prompt="abstract composition",
        provider="flux",
        model="flux-schnell",
        generated_at="2026-04-25T10:00:00Z",
        cost_usd=0.003,
        width=1024,
        height=1024,
    )


def test_cache_key_is_deterministic_and_distinct() -> None:
    a = cache_key_for(provider="flux", model="m", prompt="p", style_prefix="s", size="1024x1024")
    b = cache_key_for(provider="flux", model="m", prompt="p", style_prefix="s", size="1024x1024")
    c = cache_key_for(provider="flux", model="m", prompt="p2", style_prefix="s", size="1024x1024")
    assert a == b
    assert a != c
    assert len(a) == 64  # sha256 hex


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    cache = ImageCache(path=tmp_path)
    assert cache.get("missing-key") is None


def test_cache_put_then_get_returns_cached_marker(tmp_path: Path) -> None:
    cache = ImageCache(path=tmp_path)
    key = "abc"
    cache.put(key, _img())
    hit = cache.get(key)
    assert hit is not None
    assert hit.cached is True
    assert hit.cost_usd == 0.0    # cache hits are free
    assert hit.cache_key == key
    assert hit.data == b"png-bytes-here"
    assert hit.provider == "flux"


def test_cache_put_overwrites_existing_entry(tmp_path: Path) -> None:
    cache = ImageCache(path=tmp_path)
    cache.put("k", _img(b"first"))
    cache.put("k", _img(b"second"))
    hit = cache.get("k")
    assert hit is not None
    assert hit.data == b"second"


def test_cache_clear_removes_all_entries(tmp_path: Path) -> None:
    cache = ImageCache(path=tmp_path)
    cache.put("a", _img())
    cache.put("b", _img())
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None


def test_cache_corrupt_metadata_falls_through(tmp_path: Path) -> None:
    """A half-written cache entry should miss, not raise."""
    cache = ImageCache(path=tmp_path)
    (tmp_path / "broken.png").write_bytes(b"png")
    (tmp_path / "broken.json").write_text("not json")
    assert cache.get("broken") is None


def test_default_cache_dir_honours_workspace_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from grok_orchestra.images.cache import image_cache_dir

    monkeypatch.setenv("GROK_ORCHESTRA_WORKSPACE", str(tmp_path / "ws"))
    out = image_cache_dir()
    assert out == tmp_path / "ws" / ".cache" / "images"
    assert out.exists()
