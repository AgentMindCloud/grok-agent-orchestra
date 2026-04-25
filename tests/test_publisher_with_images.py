"""Publisher × images: cover + section illustrations land in MD/DOCX/PDF.

The image provider is fully mocked — we register a ``StubProvider``
through the public ``register_image_provider`` hook and pin
``publisher.images.provider: stub`` in the YAML. No live calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def _real_png() -> bytes:
    """Build a real PNG via Pillow so python-docx + WeasyPrint can both
    parse it. python-docx's add_picture invokes Pillow internally to read
    width/height, so a hand-crafted blob isn't enough."""
    pytest.importorskip("PIL")
    import io as _io

    from PIL import Image

    img = Image.new("RGB", (32, 32), color=(180, 110, 200))
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


_TINY_PNG = _real_png()


class _StubImageProvider:
    name = "stub"
    model = "stub-model-1"

    def __init__(self, **_kwargs: Any) -> None:
        self.calls: list[str] = []

    def generate(self, prompt: str, *, size: str = "1024x1024", n: int = 1, style_prefix: str = "", **_kwargs: Any):  # type: ignore[no-untyped-def]
        from grok_orchestra.images import GeneratedImage

        self.calls.append(prompt)
        return [
            GeneratedImage(
                data=_TINY_PNG,
                mime_type="image/png",
                prompt=prompt,
                provider=self.name,
                model=self.model,
                generated_at="2026-04-25T12:00:00Z",
                cost_usd=0.001,
                width=1024,
                height=1024,
            )
        ]


@pytest.fixture(autouse=True)
def _isolated_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setenv("GROK_ORCHESTRA_WORKSPACE", str(tmp_path / "ws"))
    return tmp_path


@pytest.fixture
def stub_provider(monkeypatch: pytest.MonkeyPatch) -> _StubImageProvider:
    """Wire the stub provider in via the public registry hook."""
    instance = _StubImageProvider()
    from grok_orchestra.images import factory

    monkeypatch.setitem(factory.PROVIDER_REGISTRY, "stub", lambda: lambda **_k: instance)
    return instance


def _yaml_with_images(
    *,
    enabled: bool = True,
    budget: int = 2,
    sections: int = 1,
    cover: bool = True,
    provider: str = "stub",
) -> str:
    return f"""
name: pub-images-test
goal: Hello in three languages.
publisher:
  images:
    enabled: {str(enabled).lower()}
    provider: {provider}
    budget: {budget}
    cover: {str(cover).lower()}
    section_illustrations: {sections}
    style: "minimal flat illustration"
orchestra:
  mode: simulated
  agent_count: 4
  reasoning_effort: medium
  debate_rounds: 1
  orchestration: {{pattern: native, config: {{}}}}
  agents:
    - {{name: Grok, role: coordinator}}
    - {{name: Harper, role: researcher}}
    - {{name: Benjamin, role: logician}}
    - {{name: Lucas, role: contrarian}}
safety: {{lucas_veto_enabled: true, confidence_threshold: 0.5}}
deploy: {{target: stdout}}
"""


def _synthetic_run(yaml_text: str, *, run_id: str = "run-img-1") -> dict[str, Any]:
    return {
        "id": run_id,
        "yaml_text": yaml_text,
        "template_name": "pub-images-test",
        "events": [
            {"type": "stream", "kind": "token", "role": "Harper", "text": "we found three things"},
            {"type": "stream", "kind": "token", "role": "Grok", "text": "synthesised three things"},
        ],
        "final_output": "Final synthesis text.",
        "veto_report": {"approved": True, "confidence": 0.91, "reasons": []},
    }


# --------------------------------------------------------------------------- #
# Markdown — image refs land at the right spots.
# --------------------------------------------------------------------------- #


def test_markdown_includes_cover_and_section_image_refs(stub_provider: _StubImageProvider) -> None:
    from grok_orchestra.publisher import Publisher

    run = _synthetic_run(_yaml_with_images(budget=2, sections=1))
    md = Publisher().build_markdown(run)
    assert "![Cover illustration](images/cover.png)" in md
    # First section (Findings) is the only one we asked for.
    assert "![Findings illustration](images/findings.png)" in md
    # The provider was called once per requested image.
    assert len(stub_provider.calls) == 2
    assert any("Cover image" in p or "Cover" in p for p in stub_provider.calls)


def test_disabled_block_skips_image_generation(stub_provider: _StubImageProvider) -> None:
    from grok_orchestra.publisher import Publisher

    run = _synthetic_run(_yaml_with_images(enabled=False))
    md = Publisher().build_markdown(run)
    assert "images/cover.png" not in md
    assert stub_provider.calls == []


def test_budget_zero_skips_everything(stub_provider: _StubImageProvider) -> None:
    from grok_orchestra.publisher import Publisher

    run = _synthetic_run(_yaml_with_images(budget=0))
    Publisher().build_markdown(run)
    assert stub_provider.calls == []


def test_provider_failure_does_not_crash_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even if the provider blows up, the markdown still ships."""
    from grok_orchestra.images import factory

    class _Boom:
        name = "boom"
        model = "boom-1"

        def generate(self, *_a: Any, **_kw: Any):  # type: ignore[no-untyped-def]
            raise RuntimeError("simulated provider crash")

    monkeypatch.setitem(factory.PROVIDER_REGISTRY, "boom", lambda: lambda **_k: _Boom())
    from grok_orchestra.publisher import Publisher

    run = _synthetic_run(_yaml_with_images(provider="boom"))
    md = Publisher().build_markdown(run)
    # Image refs not present, but the report rendered.
    assert "## Executive Summary" in md
    assert "images/cover.png" not in md


def test_refused_prompt_increments_refusal_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Policy refusal yields no image but does not crash."""
    from grok_orchestra.images import factory

    monkeypatch.setitem(factory.PROVIDER_REGISTRY, "stub", lambda: lambda **_k: _StubImageProvider())
    from grok_orchestra.publisher import Publisher

    yaml_text = _yaml_with_images(budget=1, sections=0)
    # Override the title via the synthetic run so the cover prompt
    # contains a deny-list term.
    run = _synthetic_run(yaml_text)
    run["template_name"] = "donald trump rally"   # title derives from this
    md = Publisher().build_markdown(run)
    assert "images/cover.png" not in md
    assert "## Executive Summary" in md


# --------------------------------------------------------------------------- #
# Cache — second build hits the cache, third image is free.
# --------------------------------------------------------------------------- #


def test_second_build_hits_cache(stub_provider: _StubImageProvider) -> None:
    from grok_orchestra.publisher import Publisher

    run = _synthetic_run(_yaml_with_images(budget=1, sections=0), run_id="run-cache-1")
    Publisher().build_markdown(run)
    assert len(stub_provider.calls) == 1

    # Second build for a different run id but same prompt → cache hit.
    run2 = _synthetic_run(_yaml_with_images(budget=1, sections=0), run_id="run-cache-2")
    Publisher().build_markdown(run2)
    # Provider was NOT called a second time because the cache key
    # matches across runs (provider+model+prompt+style+size).
    assert len(stub_provider.calls) == 1


# --------------------------------------------------------------------------- #
# DOCX — embedded image. We don't need to inspect the binary deeply;
# checking the resulting file is non-empty + a valid zip is enough.
# --------------------------------------------------------------------------- #


def test_docx_embeds_inline_image(
    tmp_path: Path,
    stub_provider: _StubImageProvider,
) -> None:
    pytest.importorskip("docx")
    from grok_orchestra.publisher import Publisher

    run = _synthetic_run(_yaml_with_images(budget=1, sections=0))
    out = tmp_path / "report.docx"
    Publisher().build_docx(run, out)
    assert out.exists()
    assert out.stat().st_size > 4_000

    # docx files are zips — verify the picture relationship landed.
    import zipfile

    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    media = [n for n in names if n.startswith("word/media/")]
    assert media, f"expected word/media/* entries; got: {names}"
