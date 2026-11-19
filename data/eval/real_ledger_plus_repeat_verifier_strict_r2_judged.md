# Real Ledger (LLM-as-a-Judge)

> Answers are graded by the task's deterministic verifier when one exists; the LLM judge is only a fallback for open-ended tasks. Routing was already decided, so grading never affects online behaviour.
> Judge: `external-non-qwen-judge` | sample: 50 tasks
> Judge tokens are priced with the frontier rate of pricing_file; that is an estimate, not the judge model's own tariff.

| Policy | Tasks | Judged | Judge failures | Verified | LLM judged | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | 50 | 0 | 35 | 15 | 92.00% | $0.000285 | $0.001025 | $0.002073 | $0.034024 |
| cascade | 50 | 50 | 0 | 35 | 15 | 92.00% | $0.000268 | $0.000636 | $0.002763 | $0.016915 |
| all_small | 50 | 50 | 0 | 35 | 15 | 82.00% | $0.000025 | $0.000584 | $0.000470 | $0.022941 |

> Judged success comes from the task's deterministic verifier when one exists, otherwise from a strict rubric-based LLM judge. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.

## Threshold sweep (offline replay, no extra API calls)

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.000 | 0% | 82% | $0.001476 | $0.000025 |
| 0.600 | 0% | 82% | $0.001476 | $0.000025 |
| 0.625 | 0% | 82% | $0.001476 | $0.000025 |
| 0.650 | 0% | 82% | $0.001476 | $0.000025 |
| 0.675 | 0% | 82% | $0.001476 | $0.000025 |
| 0.700 | 0% | 82% | $0.001476 | $0.000025 |
| 0.725 | 0% | 82% | $0.001476 | $0.000025 |
| 0.750 | 0% | 82% | $0.001476 | $0.000025 |
| 0.775 | 0% | 82% | $0.001476 | $0.000025 |
| 0.800 | 0% | 82% | $0.001476 | $0.000025 |
| 0.825 | 4% | 84% | $0.002641 | $0.000053 |
| 0.850 | 12% | 84% | $0.005065 | $0.000108 |
| 0.875 | 20% | 88% | $0.007890 | $0.000171 |
| 0.900 | 36% | 90% | $0.013266 | $0.000264 |
| 0.925 | 46% | 90% | $0.014227 | $0.000266 |
| 0.950 | 50% | 90% | $0.014469 | $0.000271 |
| 1.000 | 58% | 92% | $0.016368 | $0.000307 |

> Replayed from the recorded answers, verdicts and costs; the judge is never re-called, so this sweep cannot change any online route.
