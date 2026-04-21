# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-04-21

### Added
- Initial project scaffolding for Grok Agent Orchestra.
- `grok_orchestra` package with stub modules for native and simulated runtimes,
  dispatcher, patterns, safety veto, combined runtime, and streaming TUI.
- `grok-orchestra` console script entry point.
- Hard dependency on `grok-build-bridge>=0.1`; glue check in
  `grok_orchestra.__init__` fails fast with install instructions if missing.
- Apache-2.0 license, `.env.example`, `.gitignore`, CI skeleton.

[Unreleased]: https://github.com/agentmindcloud/grok-agent-orchestra/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/agentmindcloud/grok-agent-orchestra/releases/tag/v0.1.0
