# Real Ledger (LLM-as-a-Judge)

> Answers are judged offline with a strict rubric; routing was already decided, so the judge never affects online behaviour.
> Judge: `external-non-qwen-judge` | sample: 50 tasks
> Judge tokens are priced with the frontier rate of pricing_file; that is an estimate, not the judge model's own tariff.

| Policy | Tasks | Judged | Judge failures | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | 50 | 0 | 78.00% | $0.000280 | $0.001242 | $0.008910 | $0.037483 |
| cascade | 50 | 50 | 0 | 64.00% | $0.000144 | $0.000973 | $0.002317 | $0.026525 |
| all_small | 50 | 50 | 0 | 44.00% | $0.000039 | $0.001413 | $0.000916 | $0.030239 |

> Judged success comes from a strict rubric-based judge, not HTTP success. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.

## Threshold sweep (offline replay, no extra API calls)

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.000 | 0% | 44% | $0.001768 | $0.000039 |
| 0.600 | 0% | 44% | $0.001768 | $0.000039 |
| 0.625 | 0% | 44% | $0.001768 | $0.000039 |
| 0.650 | 0% | 44% | $0.001768 | $0.000039 |
| 0.675 | 2% | 46% | $0.001796 | $0.000039 |
| 0.700 | 2% | 46% | $0.001796 | $0.000039 |
| 0.725 | 6% | 50% | $0.001852 | $0.000039 |
| 0.750 | 8% | 52% | $0.001880 | $0.000039 |
| 0.775 | 10% | 54% | $0.001908 | $0.000039 |
| 0.800 | 10% | 54% | $0.001908 | $0.000039 |
| 0.825 | 20% | 60% | $0.003913 | $0.000106 |
| 0.850 | 32% | 66% | $0.007126 | $0.000171 |
| 0.875 | 58% | 70% | $0.014471 | $0.000252 |
| 0.900 | 82% | 80% | $0.018454 | $0.000286 |
| 0.925 | 92% | 84% | $0.018985 | $0.000286 |
| 0.950 | 96% | 80% | $0.020616 | $0.000299 |

> Replayed from the recorded answers, verdicts and costs; the judge is never re-called, so this sweep cannot change any online route.
