# Getting Support

Thanks for using Agent Orchestra. This page is the short answer to
"where do I ask?"

> **First**, make sure you've read the
> [Build Bridge pairing guide](docs/integrations/build-bridge.md) —
> Orchestra is a Bridge add-on and most "it doesn't import" reports
> turn out to be a missing or stale Bridge install.

## Decision tree

| What you have | Where it goes |
| --- | --- |
| A bug — something is broken or behaves unexpectedly | [GitHub Issues → bug report](https://github.com/agentmindcloud/grok-agent-orchestra/issues/new?template=bug_report.yml) |
| A feature idea | [GitHub Issues → feature request](https://github.com/agentmindcloud/grok-agent-orchestra/issues/new?template=feature_request.yml) |
| A new template you want bundled | [GitHub Issues → template proposal](https://github.com/agentmindcloud/grok-agent-orchestra/issues/new?template=template_proposal.yml) |
| A "should we…?" / "how do you all do X?" question | [GitHub Discussions](https://github.com/agentmindcloud/grok-agent-orchestra/discussions) |
| A security vulnerability | **Do not** open an issue — see [`SECURITY.md`](SECURITY.md) |
| A Bridge-side bug (Bridge raises before Orchestra runs) | [`grok-build-bridge` issues](https://github.com/agentmindcloud/grok-build-bridge/issues) |

We deliberately don't run a Discord, Slack, mailing list, or X
account for support — every question deserves a searchable answer,
and that means GitHub.

## Before filing

A short triage checklist that tends to resolve most reports
without a round-trip:

1. Run `grok-orchestra --version` and `pip show grok-build-bridge`.
   Mismatched alpha pins are the most common "broke on upgrade"
   failure.
2. Re-run with `--verbose`. Most flow control issues print a
   structured event line that names the failing role + tool.
3. Re-run with `--dry-run`. If the planner phase already errors,
   the runtime never started.
4. Check `bridge.manifest.json` (Mode B) or `orchestra-events.jsonl`
   (everything) — the receipt usually shows the exact transition.

## What we ask in a bug report

The [bug report form](https://github.com/agentmindcloud/grok-agent-orchestra/issues/new?template=bug_report.yml)
walks you through it, but the four high-signal fields are:

- **Versions** — Orchestra, Bridge, Python, OS.
- **Reproducer** — minimal YAML + the command line that triggered it.
- **Expected vs. actual** — one sentence each is fine.
- **Traceback** — full, not abridged. Redact API keys.

Issues without a reproducer are usually closed with a request for
one — there isn't a private build of Orchestra we can poke at, so
the YAML + invocation are the whole picture.

## Response times

This is a small project. Best-effort triage targets:

- Issues with a clean reproducer: response within a week.
- Discussions: response when someone has time; faster if the
  question is already answered in the docs you can link.
- Security reports: see [`SECURITY.md`](SECURITY.md).

If a triage takes longer, it's because the matching maintainer is
heads-down on something else, not because the issue is unwelcome.
A polite ping after two weeks is appropriate.

## Commercial support

There is none right now. If you need a contracted SLA, build it
on top of the Apache-2.0 license; Orchestra has no upstream that
gates re-licensed redistributions.
