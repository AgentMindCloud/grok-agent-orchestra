# Reports & export

Every run auto-writes `report.md` and `run.json` to the workspace.
PDF and DOCX render lazily on first download — `Publisher.build_pdf()`
and `Publisher.build_docx()` materialise them from the same intermediate
representation as the Markdown.

## What ships in each format

| Format | Size | Renderer | Embeds |
| --- | --- | --- | --- |
| `report.md` | ~5–40 KB | built-in | inline `![cover](images/cover.png)` |
| `report.pdf` | ~80–800 KB | WeasyPrint | embedded fonts, base-resolved image paths |
| `report.docx` | ~50–300 KB | python-docx | inline pictures via Pillow |

## Sections

The Publisher layout is fixed:

1. **Title** — derived from `template_name` + goal (sanitised).
2. **Cover image** *(optional)* — generated if `publisher.images.cover: true`.
3. **Executive Summary** — first paragraph of the synthesis.
4. **Findings** — each consensus point with citations.
5. **Disagreements** — leftover `remaining_disagreements` from the
   debate-loop, if any.
6. **Lucas verdict** — confidence + reasons (passed) or block reason (vetoed).
7. **Methodology** — orchestration mode, agents, rounds, providers used.
8. **Citations** — full URL list, deduplicated.
9. **Appendix: run trace** — link to the trace if a tracer was active.

## Configuring images

```yaml
publisher:
  images:
    enabled: true
    provider: flux            # grok | flux | stub
    budget: 3                 # max images per report
    cover: true
    section_illustrations: 2  # first N sections get an illo
    style: "minimal flat illustration, monochrome"
```

See [Image generation](image-generation.md) for provider details.

## Programmatic API

```python
from grok_orchestra.publisher import Publisher

pub = Publisher()
md   = pub.build_markdown(run)        # str
path = pub.build_pdf(run, "report.pdf")
path = pub.build_docx(run, "report.docx")
```

`run` is the dict-shaped `OrchestraResult.to_dict()` — what
`run.json` already contains. Any persisted run can be re-rendered.

## Extras to install

```bash
pip install "grok-agent-orchestra[publish]"   # WeasyPrint + python-docx + Pillow
```

WeasyPrint depends on system-level libraries (Cairo, Pango). On Debian:

```bash
sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0
```

The Docker image includes them — `deploy/docker.md` for details.

## See also

- [Image generation](image-generation.md) — cover + illustrations.
- [Events](../reference/events.md) — `report_exported` event.
