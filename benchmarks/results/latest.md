# Template-coverage benchmark

Deterministic baseline benchmark — exercises every shipped template against
the Orchestra JSON Schema. Runs without API keys.

## Headline numbers

- Templates exercised: **18**
- Pass rate: **100%** (18/18)
- Parse latency p50: **4.33 ms**
- Parse latency max: **5.85 ms**
- `orchestra` block coverage: **100%**
- `safety` block coverage: **100%**

## Per-template results

| Template | OK | Parse (ms) | Notes |
| --- | --- | --- | --- |
| `combined-coder-critic.yaml` | ✓ | 5.85 |  |
| `combined-trendseeker.yaml` | ✓ | 5.53 |  |
| `competitive-analysis.yaml` | ✓ | 4.39 |  |
| `debate-loop-with-local-docs.yaml` | ✓ | 4.75 |  |
| `deep-research-hierarchical.yaml` | ✓ | 4.26 |  |
| `due-diligence-investor-memo.yaml` | ✓ | 4.58 |  |
| `orchestra-debate-loop-policy.yaml` | ✓ | 3.84 |  |
| `orchestra-dynamic-spawn-trend-analyzer.yaml` | ✓ | 3.24 |  |
| `orchestra-hierarchical-research.yaml` | ✓ | 4.01 |  |
| `orchestra-native-16.yaml` | ✓ | 3.07 |  |
| `orchestra-native-4.yaml` | ✓ | 2.69 |  |
| `orchestra-parallel-tools-fact-check.yaml` | ✓ | 3.19 |  |
| `orchestra-recovery-resilient.yaml` | ✓ | 2.83 |  |
| `orchestra-simulated-truthseeker.yaml` | ✓ | 4.06 |  |
| `paper-summarizer.yaml` | ✓ | 4.44 |  |
| `product-launch-brief.yaml` | ✓ | 4.43 |  |
| `red-team-the-plan.yaml` | ✓ | 4.50 |  |
| `weekly-news-digest.yaml` | ✓ | 4.52 |  |

## How this fits the larger benchmark suite

The four-system head-to-head harness (`benchmarks/harness.py`) measures qualitative differences between Orchestra and competing agent frameworks. It needs real API keys and is gated behind the monthly CI workflow.

*This* benchmark is the always-green baseline — every PR can run it locally and verify that no template regression slipped past code review.
