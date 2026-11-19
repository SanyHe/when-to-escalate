# Real Ledger (LLM-as-a-Judge)

> Answers are graded by the task's deterministic verifier when one exists; the LLM judge is only a fallback for open-ended tasks. Routing was already decided, so grading never affects online behaviour.
> Judge: `external-non-qwen-judge` | sample: 50 tasks
> Judge tokens are priced with the frontier rate of pricing_file; that is an estimate, not the judge model's own tariff.

| Policy | Tasks | Judged | Judge failures | Verified | LLM judged | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | 50 | 0 | 35 | 15 | 84.00% | $0.000254 | $0.001019 | $0.004351 | $0.032133 |
| cascade | 50 | 50 | 0 | 35 | 15 | 96.00% | $0.000290 | $0.000622 | $0.001274 | $0.015918 |
| all_small | 50 | 50 | 0 | 35 | 15 | 80.00% | $0.000024 | $0.000493 | $0.000506 | $0.018753 |

> Judged success comes from the task's deterministic verifier when one exists, otherwise from a strict rubric-based LLM judge. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.

## Threshold sweep (offline replay, no extra API calls)

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.000 | 0% | 80% | $0.001476 | $0.000024 |
| 0.600 | 0% | 80% | $0.001476 | $0.000024 |
| 0.625 | 0% | 80% | $0.001476 | $0.000024 |
| 0.650 | 0% | 80% | $0.001476 | $0.000024 |
| 0.675 | 0% | 80% | $0.001476 | $0.000024 |
| 0.700 | 0% | 80% | $0.001476 | $0.000024 |
| 0.725 | 0% | 80% | $0.001476 | $0.000024 |
| 0.750 | 0% | 80% | $0.001476 | $0.000024 |
| 0.775 | 0% | 80% | $0.001476 | $0.000024 |
| 0.800 | 0% | 80% | $0.001476 | $0.000024 |
| 0.825 | 4% | 82% | $0.002643 | $0.000054 |
| 0.850 | 14% | 84% | $0.005900 | $0.000129 |
| 0.875 | 20% | 82% | $0.008010 | $0.000147 |
| 0.900 | 36% | 86% | $0.013001 | $0.000218 |
| 0.925 | 44% | 84% | $0.013952 | $0.000222 |
| 0.950 | 48% | 84% | $0.014170 | $0.000227 |
| 1.000 | 58% | 84% | $0.016199 | $0.000273 |

> Replayed from the recorded answers, verdicts and costs; the judge is never re-called, so this sweep cannot change any online route.
