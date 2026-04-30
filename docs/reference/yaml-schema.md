# YAML schema

Every Orchestra spec is validated against `grok_orchestra/schema/`
before a run starts. `grok-orchestra validate -f spec.yaml` runs the
same check the runtime would, without invoking any provider.

## Top-level shape

```yaml
name: my-run                  # required, slug
goal: "..."                   # required, free-text user goal

orchestra:                    # required block
  mode: native | simulated | auto
  agent_count: 4
  reasoning_effort: low | medium | high
  debate_rounds: 3
  orchestration:
    pattern: native | hierarchical | dynamic-spawn | debate-loop | parallel-tools
    config: { ... }           # pattern-specific keys
  agents:                     # role bindings
    - { name: Grok,     role: coordinator }
    - { name: Harper,   role: researcher }
    - { name: Benjamin, role: logician }
    - { name: Lucas,    role: contrarian }
  llm:                        # optional, default = grok native
    default: { provider, model, base_url? }
    role_overrides: { Harper: {...}, Benjamin: {...}, Lucas: {...} }

sources:                      # optional, list
  - kind: web_search | local_docs
    ...                       # backend-specific keys

publisher:                    # optional, lazy
  images:
    enabled: bool
    provider: grok | flux | stub
    budget: int
    cover: bool
    section_illustrations: int
    style: str

safety:
  lucas_veto_enabled: true    # default
  confidence_threshold: 0.7   # default

deploy:
  target: stdout | file | x | ...
```

## Pattern-specific config

=== "native"

    ```yaml
    orchestration:
      pattern: native
      config: {}              # no extra keys; uses xAI native multi-agent endpoint
    ```

=== "debate-loop"

    ```yaml
    orchestration:
      pattern: debate-loop
      config:
        iterations: 5
        consensus_threshold: 0.80
        max_rounds: 1
    ```

=== "dynamic-spawn"

    ```yaml
    orchestration:
      pattern: dynamic-spawn
      config:
        max_parallel: 4
        shard_strategy: planner | enumeration | yaml
        merge_role: Grok
    ```

=== "hierarchical"

    ```yaml
    orchestration:
      pattern: hierarchical
      config:
        teams:
          - { name: ResearchTeam, members: [Harper, Benjamin] }
          - { name: CritiqueTeam, members: [Lucas, Grok] }
    ```

## Validation guarantees

The validator catches:

- Missing required keys (`name`, `goal`, `orchestra`).
- Invalid enum values (e.g. `pattern: yolo`).
- Type mismatches (e.g. `iterations: "five"`).
- Role names not matching the canonical four (Grok, Harper, Benjamin, Lucas).
- Forbidden cross-references (e.g. `merge_role: NotARealAgent`).

It does **not** catch:

- Whether the configured provider is reachable — that's `doctor`.
- Whether the configured model exists — that's `models test`.
- Semantic correctness of `goal` — that's the job of the agents.

## Programmatic validation

```python
from grok_orchestra.parser import parse_yaml, ValidationError

try:
    config = parse_yaml(open("spec.yaml"))
except ValidationError as e:
    print(e.errors)
```
