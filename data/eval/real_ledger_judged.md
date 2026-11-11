# Real Ledger (LLM-as-a-Judge)

> Answers are judged offline with a strict rubric; routing was already decided, so the judge never affects online behaviour.
> Judge: `external-non-qwen-judge` | sample: 50 tasks
> Judge tokens are priced with the frontier rate of pricing_file; that is an estimate, not the judge model's own tariff.

| Policy | Tasks | Judged | Judge failures | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | 50 | 0 | 78.00% | $0.000263 | $0.001340 | $0.008887 | $0.042023 |
| cascade | 50 | 50 | 0 | 50.00% | $0.000382 | $0.001743 | $0.006235 | $0.034019 |
| all_small | 50 | 50 | 0 | 28.00% | $0.000126 | $0.002542 | $0.005728 | $0.033827 |

> Judged success comes from a strict rubric-based judge, not HTTP success. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.

## Threshold sweep (offline replay, no extra API calls)

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.000 | 0% | 28% | $0.007486 | $0.000126 |
| 0.600 | 0% | 28% | $0.007486 | $0.000126 |
| 0.625 | 0% | 28% | $0.007486 | $0.000126 |
| 0.650 | 0% | 28% | $0.007486 | $0.000126 |
| 0.675 | 0% | 28% | $0.007486 | $0.000126 |
| 0.700 | 0% | 28% | $0.007486 | $0.000126 |
| 0.725 | 0% | 28% | $0.007486 | $0.000126 |
| 0.750 | 0% | 28% | $0.007486 | $0.000126 |
| 0.775 | 0% | 28% | $0.007486 | $0.000126 |
| 0.800 | 0% | 28% | $0.007486 | $0.000126 |
| 0.825 | 14% | 36% | $0.010672 | $0.000222 |
| 0.850 | 34% | 50% | $0.015950 | $0.000351 |
| 0.875 | 62% | 66% | $0.021800 | $0.000411 |
| 0.900 | 74% | 72% | $0.023331 | $0.000407 |
| 0.925 | 96% | 80% | $0.024797 | $0.000380 |
| 0.950 | 98% | 78% | $0.025682 | $0.000382 |

> Replayed from the recorded answers, verdicts and costs; the judge is never re-called, so this sweep cannot change any online route.
