# Real Ledger (LLM-as-a-Judge)

> Answers are graded by the task's deterministic verifier when one exists; the LLM judge is only a fallback for open-ended tasks. Routing was already decided, so grading never affects online behaviour.
> Judge: `external-non-qwen-judge` | sample: 50 tasks
> Judge tokens are priced with the frontier rate of pricing_file; that is an estimate, not the judge model's own tariff.

| Policy | Tasks | Judged | Judge failures | Verified | LLM judged | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | 50 | 0 | 35 | 15 | 92.00% | $0.000268 | $0.000715 | $0.003364 | $0.020585 |
| cascade | 50 | 50 | 0 | 35 | 15 | 88.00% | $0.000121 | $0.000506 | $0.000501 | $0.016919 |
| all_small | 50 | 50 | 0 | 35 | 15 | 80.00% | $0.000023 | $0.000460 | $0.000534 | $0.017478 |

> Judged success comes from the task's deterministic verifier when one exists, otherwise from a strict rubric-based LLM judge. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.

## Threshold sweep (offline replay, no extra API calls)

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.000 | 0% | 80% | $0.001471 | $0.000023 |
| 0.600 | 0% | 80% | $0.001471 | $0.000023 |
| 0.625 | 0% | 80% | $0.001471 | $0.000023 |
| 0.650 | 0% | 80% | $0.001471 | $0.000023 |
| 0.675 | 0% | 80% | $0.001471 | $0.000023 |
| 0.700 | 0% | 80% | $0.001471 | $0.000023 |
| 0.725 | 0% | 80% | $0.001471 | $0.000023 |
| 0.750 | 0% | 80% | $0.001471 | $0.000023 |
| 0.775 | 0% | 80% | $0.001471 | $0.000023 |
| 0.800 | 0% | 80% | $0.001471 | $0.000023 |
| 0.825 | 4% | 80% | $0.002705 | $0.000037 |
| 0.850 | 12% | 82% | $0.005256 | $0.000077 |
| 0.875 | 20% | 84% | $0.008253 | $0.000148 |
| 0.900 | 36% | 88% | $0.013555 | $0.000246 |
| 0.925 | 46% | 90% | $0.014592 | $0.000243 |
| 0.950 | 50% | 90% | $0.014892 | $0.000250 |
| 1.000 | 58% | 92% | $0.016853 | $0.000287 |

> Replayed from the recorded answers, verdicts and costs; the judge is never re-called, so this sweep cannot change any online route.
