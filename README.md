# Grok Agent Orchestra

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-1F6FEB?style=for-the-badge)
![Multi-Agent](https://img.shields.io/badge/Grok-4.20%20Multi--Agent-8B5CF6?style=for-the-badge)
![Simulated Debate](https://img.shields.io/badge/Simulated-Debate-B45309?style=for-the-badge)
![Lucas Gate](https://img.shields.io/badge/Lucas-Gate-C62828?style=for-the-badge)
![Dry Run](https://img.shields.io/badge/Dry--Run-tokenless-0A7F5A?style=for-the-badge)
![VS%20Code](https://img.shields.io/badge/VS%20Code-schema%20%2B%20snippets-007ACC?style=for-the-badge)

## One YAML. Two runtimes. Four named agents. Five orchestration patterns. One final veto.

**Grok Agent Orchestra** is the orchestration and safety layer for Grok 4.20 workflows.  
It lets the same spec drive either a native xAI multi-agent execution or a visible simulated debate between **Grok**, **Harper**, **Benjamin**, and **Lucas**—with every route converging on a mandatory fail-closed safety review.

---

## Signal map

```mermaidflowchart TBY[YAML Spec] --> M{Mode Resolver}M --> N[Native]M --> S[Simulated]subgraph P[Patterns]
      P1[hierarchical]
      P2[dynamic-spawn]
      P3[debate-loop]
      P4[parallel-tools]
      P5[recovery]
    end

    N --> P
    S --> A1[Grok]
    S --> A2[Harper]
    S --> A3[Benjamin]
    S --> A4[Lucas]

    P --> R[Run Output]
    A1 --> R
    A2 --> R
    A3 --> R

    R --> V[Lucas Veto]
    A4 --> V

    V -->|safe| D[Deploy / X / Webhook]
    V -->|unsafe| X[Block + Exit 4]
```

---

## Why this repo is different

> **Bridge generates. Orchestra arbitrates.**  
> This repo is the sibling that wraps Grok native multi-agent execution and a visible four-role debate behind the same YAML, then forces everything through a final Lucas safety gate before release.

---

## Capabilities

| Layer | Included |
|---|---|
| Spec | YAML parsing with Orchestra extensions layered over sibling Bridge fields |
| Runtime | Native multi-agent flow and simulated named-role debate |
| Orchestration | 5 composable patterns, each intentionally small and understandable |
| Safety | Strict-JSON Lucas veto, retry handling, low-confidence downgrade to `safe=false` |
| UX | Flicker-free Rich Live TUI plus non-TTY structured logging |
| Editor | JSON schema, markdown descriptions, and YAML snippets for VS Code |

---

## Demo

```bash
grok-orchestra init orchestra-native-4 --out my-spec.yaml && grok-orchestra run my-spec.yaml --dry-run
```

---

## Mode comparison

| Dimension | `native` | `simulated` |
|---|---|---|
| Execution | xAI-native multi-agent endpoint | Visible prompt-simulated role debate |
| Agent count | 4 or 16 | Four named roles |
| Auditability | Endpoint-centric | Transcript-centric |
| Best use | Native multi-agent runs | Transparent, inspectable reasoning |

---

## Why advanced users will respect it

- **Mandatory veto on every pattern** instead of optional “safety later”.
- **Re-entrant Live UI** that keeps a combined runtime coherent instead of tearing down panels between stages.
- **Dry-run replay clients** keyed by prompt shape so orchestration can be previewed offline.
- **Typed CLI exit behavior** for automation-friendly pipeline control.

---

## Repo snapshot

- **Tech stack:** Python 3.10+ · xAI-SDK · Typer · Rich · JSONSchema · Tenacity  
- **Version:** 0.1.0  
- **License:** Apache-2.0  
- **Commit activity:** 17 commits in the last 30 days  
- **Best audience:** Python teams shipping Grok-powered agents into production systems with public-facing consequences
