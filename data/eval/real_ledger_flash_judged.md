# Real Ledger (LLM-as-a-Judge)

> Answers are judged offline with a strict rubric; routing was already decided, so the judge never affects online behaviour.
> Judge: `external-non-qwen-judge` | sample: 50 tasks
> Judge tokens are priced with the frontier rate of pricing_file; that is an estimate, not the judge model's own tariff.

| Policy | Tasks | Judged | Judge failures | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | 50 | 0 | 80.00% | $0.000256 | $0.001069 | $0.008645 | $0.032521 |
| cascade | 50 | 50 | 0 | 46.00% | $0.000312 | $0.001780 | $0.005765 | $0.033781 |
| all_small | 50 | 50 | 0 | 10.00% | $0.000031 | $0.004562 | $0.000794 | $0.022652 |

> Judged success comes from a strict rubric-based judge, not HTTP success. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.

## Threshold sweep (offline replay, no extra API calls)

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.000 | 0% | 10% | $0.000951 | $0.000031 |
| 0.600 | 0% | 10% | $0.000951 | $0.000031 |
| 0.625 | 0% | 10% | $0.000951 | $0.000031 |
| 0.650 | 0% | 10% | $0.000951 | $0.000031 |
| 0.675 | 0% | 10% | $0.000951 | $0.000031 |
| 0.700 | 0% | 10% | $0.000951 | $0.000031 |
| 0.725 | 0% | 10% | $0.000951 | $0.000031 |
| 0.750 | 0% | 10% | $0.000951 | $0.000031 |
| 0.775 | 4% | 10% | $0.002512 | $0.000176 |
| 0.800 | 16% | 16% | $0.005179 | $0.000261 |
| 0.825 | 30% | 28% | $0.007134 | $0.000234 |
| 0.850 | 52% | 44% | $0.012203 | $0.000342 |
| 0.875 | 72% | 58% | $0.015965 | $0.000323 |
| 0.900 | 78% | 64% | $0.016400 | $0.000307 |
| 0.925 | 82% | 68% | $0.016676 | $0.000299 |
| 0.950 | 98% | 78% | $0.019729 | $0.000274 |
| 1.000 | 100% | 80% | $0.019817 | $0.000270 |

> Replayed from the recorded answers, verdicts and costs; the judge is never re-called, so this sweep cannot change any online route.
