# Grok Agent Orchestra

> Grok 4.20 multi-agent orchestration on top of [Grok Build Bridge](https://github.com/agentmindcloud/grok-build-bridge).

Grok Agent Orchestra is an Apache-2.0 Python 3.10+ framework for orchestrating
Grok 4.20 agents. It sits on top of Grok Build Bridge (v0.1+) and adds:

- **xAI-native** multi-agent execution against `grok-4.20-multi-agent-0309`.
- **Prompt-simulated** debate between named roles — Grok, Harper, Benjamin, and
  Lucas — with a visible thought-chain.
- Pattern library: hierarchical, dynamic, debate-loop, parallel, and recovery.
- A **Lucas veto gate** for safety-critical outputs.
- Combined Bridge + Orchestra runtime and a live Rich-powered TUI.

## Status

Pre-alpha scaffolding. Full docs and usage examples land in Session 12.
This stub exists to let Bridge consumers pin the package early.

## Install

```bash
pip install grok-agent-orchestra
```

Grok Build Bridge is a hard dependency — Orchestra never duplicates Bridge code.

## Quickstart

```bash
cp .env.example .env
# edit .env, set XAI_API_KEY
grok-orchestra --help
```

## License

Apache 2.0 — see [LICENSE](LICENSE). Copyright (c) 2026 Jan Solo / AgentMindCloud.
