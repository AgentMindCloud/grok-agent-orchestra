# Multi-provider LLM

Grok is the default and the executive role's strict mode. Every other
role can point at any provider that LiteLLM speaks — OpenAI, Anthropic,
Mistral, Cohere, Bedrock, Azure OpenAI, Ollama, vLLM, Together, Groq.

## Two adapter modes

| Mode | When | What it uses |
| --- | --- | --- |
| **Native Grok** | All roles use `grok-*` | xAI SDK directly — full multi-agent endpoint, parallel tools, reasoning effort. |
| **LiteLLM adapter** | Any role points at non-Grok | `litellm.completion(...)` with role-specific config. |

The framework picks the mode automatically based on the resolved
`role_models` map.

## Mix-and-match example

```yaml
orchestra:
  llm:
    default:
      provider: xai
      model: grok-4-0709
    role_overrides:
      Harper:
        provider: anthropic
        model: claude-sonnet-4-6
      Benjamin:
        provider: openai
        model: gpt-4.1-mini
      Lucas:
        provider: xai
        model: grok-4.20-0309         # always strict for the veto
```

??? tip "Cheaper Harper, strict Lucas"
    A common pattern: route the chatty researcher (Harper) through a
    cheap provider while keeping Grok on the executive turn and the
    veto. Costs drop ~60% on heavy templates.

## Local tier — Ollama

```bash
ollama pull llama3.1:8b
pip install "grok-agent-orchestra[adapters]"
```

```yaml
orchestra:
  llm:
    default:
      provider: ollama
      model: llama3.1:8b
      base_url: http://localhost:11434
```

`grok-orchestra doctor` checks that `ollama` is reachable.

## Per-provider env vars

| Provider | Env var |
| --- | --- |
| xAI | `XAI_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Mistral | `MISTRAL_API_KEY` |
| Cohere | `COHERE_API_KEY` |
| Groq | `GROQ_API_KEY` |
| Together | `TOGETHER_API_KEY` |
| Bedrock | `AWS_*` standard chain |
| Azure OpenAI | `AZURE_OPENAI_*` |
| Ollama | none — local |

The framework never hardcodes a key. Every provider's own SDK reads
its env var.

## See also

- [Four roles](../concepts/four-roles.md) — what each role does.
- [Tracing](tracing.md) — provider + cost per span.
