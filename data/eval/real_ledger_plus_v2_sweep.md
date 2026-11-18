# Real Ledger (LLM-as-a-Judge)

> Answers are graded by the task's deterministic verifier when one exists; the LLM judge is only a fallback for open-ended tasks. Routing was already decided, so grading never affects online behaviour.
> Judge: `external-non-qwen-judge` | sample: 50 tasks
> Judge tokens are priced with the frontier rate of pricing_file; that is an estimate, not the judge model's own tariff.

| Policy | Tasks | Judged | Judge failures | Verified | LLM judged | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | 50 | 0 | 35 | 15 | 90.00% | $0.000279 | $0.000662 | $0.002661 | $0.017249 |
| cascade | 50 | 50 | 0 | 35 | 15 | 80.00% | $0.000098 | $0.000675 | $0.001246 | $0.023089 |
| all_small | 50 | 50 | 0 | 35 | 15 | 82.00% | $0.000024 | $0.000401 | $0.000473 | $0.015442 |

> Judged success comes from the task's deterministic verifier when one exists, otherwise from a strict rubric-based LLM judge. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.

## Threshold sweep (offline replay, no extra API calls)

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.000 | 4% | 86% | $0.003052 | $0.000063 |
| 0.600 | 4% | 86% | $0.003052 | $0.000063 |
| 0.625 | 4% | 86% | $0.003052 | $0.000063 |
| 0.650 | 4% | 86% | $0.003052 | $0.000063 |
| 0.675 | 4% | 86% | $0.003052 | $0.000063 |
| 0.700 | 4% | 86% | $0.003052 | $0.000063 |
| 0.725 | 4% | 86% | $0.003052 | $0.000063 |
| 0.750 | 4% | 86% | $0.003052 | $0.000063 |
| 0.775 | 4% | 86% | $0.003052 | $0.000063 |
| 0.800 | 4% | 86% | $0.003052 | $0.000063 |
| 0.825 | 8% | 88% | $0.004246 | $0.000090 |
| 0.850 | 14% | 90% | $0.006031 | $0.000127 |
| 0.875 | 22% | 90% | $0.008971 | $0.000177 |
| 0.900 | 36% | 90% | $0.013115 | $0.000251 |
| 0.925 | 46% | 90% | $0.014080 | $0.000251 |
| 0.950 | 50% | 90% | $0.014348 | $0.000257 |
| 1.000 | 58% | 90% | $0.016372 | $0.000299 |

> Replayed from the recorded answers, verdicts and costs; the judge is never re-called, so this sweep cannot change any online route.
