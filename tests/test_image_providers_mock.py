"""Image provider tests — every backend mocked, no live calls."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

# --------------------------------------------------------------------------- #
# Factory.
# --------------------------------------------------------------------------- #


def test_factory_resolves_known_providers() -> None:
    from grok_orchestra.images import resolve_image_provider
    from grok_orchestra.images.flux_provider import FluxReplicateProvider
    from grok_orchestra.images.grok_provider import GrokImageProvider

    assert isinstance(resolve_image_provider("grok"), GrokImageProvider)
    # Flux needs a token-or-client to construct; pass a fake client so we
    # don't trip the env-var guard.
    assert isinstance(
        resolve_image_provider("flux", client=MagicMock()),
        FluxReplicateProvider,
    )


def test_factory_raises_on_unknown_provider() -> None:
    from grok_orchestra.images import ImageError, resolve_image_provider

    with pytest.raises(ImageError, match="unknown image provider"):
        resolve_image_provider("nope")


# --------------------------------------------------------------------------- #
# Grok stub — must fail loud per the anti-pattern.
# --------------------------------------------------------------------------- #


def test_grok_provider_raises_with_pointer_to_flux() -> None:
    from grok_orchestra.images import GrokImageProvider, ImageError

    with pytest.raises(ImageError, match="provider: flux"):
        GrokImageProvider().generate("a city skyline")


# --------------------------------------------------------------------------- #
# Flux + Replicate — completely mocked.
# --------------------------------------------------------------------------- #


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"x" * 64


def _mock_urlopen(_req: Any, timeout: float = 0) -> Any:
    del timeout

    class _Resp:
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

        def read(self) -> bytes:
            return _PNG_MAGIC

    return _Resp()


def test_flux_generates_image_via_replicate_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`replicate.run` is called once with the right shape."""
    from grok_orchestra.images.flux_provider import FluxReplicateProvider

    fake_client = MagicMock()
    fake_client.run.return_value = ["https://example.com/out.png"]

    provider = FluxReplicateProvider(client=fake_client, urlopen=_mock_urlopen)
    images = provider.generate("a quiet harbor", style_prefix="abstract", n=1)
    assert len(images) == 1
    assert images[0].data == _PNG_MAGIC
    assert images[0].provider == "flux"
    assert images[0].cost_usd > 0
    # The full prompt should include the style prefix.
    fake_client.run.assert_called_once()
    call_kwargs = fake_client.run.call_args.kwargs
    assert call_kwargs["input"]["prompt"].startswith("abstract")
    assert call_kwargs["input"]["num_outputs"] == 1


def test_flux_handles_object_with_url_attribute() -> None:
    """Newer replicate SDK returns FileOutput objects with a .url attr."""
    from grok_orchestra.images.flux_provider import FluxReplicateProvider

    file_out = MagicMock()
    file_out.url = "https://example.com/x.png"
    fake_client = MagicMock()
    fake_client.run.return_value = [file_out]
    provider = FluxReplicateProvider(client=fake_client, urlopen=_mock_urlopen)
    images = provider.generate("anything")
    assert images and images[0].data == _PNG_MAGIC


def test_flux_raises_image_error_when_token_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No env token + no injected client ⇒ explicit ImageError."""
    from grok_orchestra.images import ImageError
    from grok_orchestra.images.flux_provider import FluxReplicateProvider

    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    provider = FluxReplicateProvider()
    with pytest.raises(ImageError, match="REPLICATE_API_TOKEN"):
        provider.generate("anything")


def test_flux_wraps_provider_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from grok_orchestra.images import ImageError
    from grok_orchestra.images.flux_provider import FluxReplicateProvider

    fake_client = MagicMock()
    fake_client.run.side_effect = RuntimeError("rate limited")
    provider = FluxReplicateProvider(client=fake_client, urlopen=_mock_urlopen)
    with pytest.raises(ImageError, match="Flux generation failed"):
        provider.generate("anything")


def test_flux_returns_empty_when_replicate_yields_nothing() -> None:
    from grok_orchestra.images import ImageError
    from grok_orchestra.images.flux_provider import FluxReplicateProvider

    fake_client = MagicMock()
    fake_client.run.return_value = []
    provider = FluxReplicateProvider(client=fake_client, urlopen=_mock_urlopen)
    with pytest.raises(ImageError, match="no image URLs"):
        provider.generate("anything")


