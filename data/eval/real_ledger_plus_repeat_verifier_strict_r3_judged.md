# Real Ledger (LLM-as-a-Judge)

> Answers are graded by the task's deterministic verifier when one exists; the LLM judge is only a fallback for open-ended tasks. Routing was already decided, so grading never affects online behaviour.
> Judge: `external-non-qwen-judge` | sample: 50 tasks
> Judge tokens are priced with the frontier rate of pricing_file; that is an estimate, not the judge model's own tariff.

| Policy | Tasks | Judged | Judge failures | Verified | LLM judged | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | 50 | 0 | 35 | 15 | 88.00% | $0.000275 | $0.000667 | $0.004225 | $0.017226 |
| cascade | 50 | 50 | 0 | 35 | 15 | 94.00% | $0.000271 | $0.000704 | $0.002773 | $0.020353 |
| all_small | 50 | 50 | 0 | 35 | 15 | 82.00% | $0.000024 | $0.000390 | $0.000469 | $0.015003 |

> Judged success comes from the task's deterministic verifier when one exists, otherwise from a strict rubric-based LLM judge. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.

## Threshold sweep (offline replay, no extra API calls)

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.000 | 0% | 82% | $0.001466 | $0.000024 |
| 0.600 | 0% | 82% | $0.001466 | $0.000024 |
| 0.625 | 0% | 82% | $0.001466 | $0.000024 |
| 0.650 | 0% | 82% | $0.001466 | $0.000024 |
| 0.675 | 0% | 82% | $0.001466 | $0.000024 |
| 0.700 | 0% | 82% | $0.001466 | $0.000024 |
| 0.725 | 0% | 82% | $0.001466 | $0.000024 |
| 0.750 | 0% | 82% | $0.001466 | $0.000024 |
| 0.775 | 0% | 82% | $0.001466 | $0.000024 |
| 0.800 | 0% | 82% | $0.001466 | $0.000024 |
| 0.825 | 4% | 84% | $0.002735 | $0.000055 |
| 0.850 | 12% | 86% | $0.005473 | $0.000103 |
| 0.875 | 18% | 86% | $0.007519 | $0.000119 |
| 0.900 | 36% | 88% | $0.013681 | $0.000236 |
| 0.925 | 46% | 86% | $0.014969 | $0.000242 |
| 0.950 | 50% | 86% | $0.015308 | $0.000250 |
| 1.000 | 58% | 88% | $0.017491 | $0.000294 |

> Replayed from the recorded answers, verdicts and costs; the judge is never re-called, so this sweep cannot change any online route.
