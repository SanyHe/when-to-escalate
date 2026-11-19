# Real Ledger (LLM-as-a-Judge)

> Answers are graded by the task's deterministic verifier when one exists; the LLM judge is only a fallback for open-ended tasks. Routing was already decided, so grading never affects online behaviour.
> Judge: `external-non-qwen-judge` | sample: 50 tasks
> Judge tokens are priced with the frontier rate of pricing_file; that is an estimate, not the judge model's own tariff.

| Policy | Tasks | Judged | Judge failures | Verified | LLM judged | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | 50 | 0 | 35 | 15 | 92.00% | $0.000293 | $0.000812 | $0.001740 | $0.023883 |
| cascade | 50 | 50 | 0 | 35 | 15 | 86.00% | $0.000108 | $0.000568 | $0.001071 | $0.019744 |
| all_small | 50 | 50 | 0 | 35 | 15 | 80.00% | $0.000023 | $0.000544 | $0.000544 | $0.020856 |

> Judged success comes from the task's deterministic verifier when one exists, otherwise from a strict rubric-based LLM judge. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.

## Threshold sweep (offline replay, no extra API calls)

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.000 | 0% | 80% | $0.001463 | $0.000023 |
| 0.600 | 0% | 80% | $0.001463 | $0.000023 |
| 0.625 | 0% | 80% | $0.001463 | $0.000023 |
| 0.650 | 0% | 80% | $0.001463 | $0.000023 |
| 0.675 | 0% | 80% | $0.001463 | $0.000023 |
| 0.700 | 0% | 80% | $0.001463 | $0.000023 |
| 0.725 | 0% | 80% | $0.001463 | $0.000023 |
| 0.750 | 0% | 80% | $0.001463 | $0.000023 |
| 0.775 | 0% | 80% | $0.001463 | $0.000023 |
| 0.800 | 0% | 80% | $0.001463 | $0.000023 |
| 0.825 | 4% | 82% | $0.002759 | $0.000056 |
| 0.850 | 12% | 86% | $0.005150 | $0.000112 |
| 0.875 | 20% | 88% | $0.008107 | $0.000160 |
| 0.900 | 36% | 92% | $0.013158 | $0.000266 |
| 0.925 | 44% | 92% | $0.013255 | $0.000267 |
| 0.950 | 50% | 92% | $0.014348 | $0.000274 |
| 1.000 | 58% | 92% | $0.016361 | $0.000314 |

> Replayed from the recorded answers, verdicts and costs; the judge is never re-called, so this sweep cannot change any online route.
