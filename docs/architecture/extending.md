# Extending

Three Protocols cover the points where you'd want to plug something
new in: `Source`, `LLMClient`, `ImageProvider`. Tracers also have a
`Tracer` Protocol but the three shipped backends (LangSmith, Langfuse,
OTLP) cover the production cases.

## Add a Source backend

Sources answer Harper's queries — web search, local docs, your
private knowledge base.

```python
# my_source.py
from grok_orchestra.sources import Source, Hit

class CorpSearch:
    name = "corp"

    def __init__(self, *, api_url: str, **_kw) -> None:
        self.api_url = api_url

    def query(self, q: str, *, k: int = 8) -> list[Hit]:
        # call your internal search; map to Hit(title, url, snippet)
        ...
```

Register it:

```python
# in your project's __init__ or via entry-point
from grok_orchestra.sources import factory
factory.SOURCE_REGISTRY["corp"] = lambda **kw: CorpSearch(**kw)
```

Use it in YAML:

```yaml
sources:
  - kind: corp
    api_url: https://search.internal
```

## Add an LLM provider

If LiteLLM doesn't cover it, implement `LLMClient`:

```python
# my_llm.py
from grok_orchestra.llm import LLMClient, ChatMessage, ChatResponse

class MyClient:
    name = "myco"
    model = "myco-7b"

    def chat(self, messages: list[ChatMessage], **kw) -> ChatResponse:
        ...

    def stream(self, messages: list[ChatMessage], **kw):
        ...
```

Register via `grok_orchestra.llm.registry.PROVIDER_REGISTRY["myco"] = ...`

## Add an Image provider

Implement `ImageProvider`:

```python
from grok_orchestra.images import ImageProvider, GeneratedImage

class MyImg:
    name = "myimg"
    model = "myimg-v1"

    def generate(self, prompt: str, *, size="1024x1024", n=1, **kw) -> list[GeneratedImage]:
        ...
```

Register via `grok_orchestra.images.factory.PROVIDER_REGISTRY`.

## Add a custom orchestration pattern

Patterns live in `grok_orchestra/patterns.py`. A pattern is a callable:

```python
def my_pattern(config, client, *, event_callback=None) -> OrchestraResult:
    # emit role_started/role_completed events as you go
    # call client to generate role outputs
    # invoke safety_lucas_veto at the end
    # return OrchestraResult(...)
    ...
```

Register it in `PATTERN_REGISTRY` so YAML can pick it via
`orchestration.pattern: my-pattern`.

## Where to put tests

Mirror the package layout under `tests/`. Stub external services —
**no live API calls in CI**. The repo has a long-standing rule:
every key is BYOK, every test is fully mocked.

See `tests/test_sources_mock.py`, `tests/test_image_providers_mock.py`,
and `tests/test_tracing_mock.py` for the canonical patterns.

## See also

- [Python API](../reference/python-api.md) — Protocol signatures.
- [Contributing](../contributing/index.md) — PR flow.
