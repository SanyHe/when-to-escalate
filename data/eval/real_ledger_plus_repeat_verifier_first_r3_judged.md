# Real Ledger (LLM-as-a-Judge)

> Answers are graded by the task's deterministic verifier when one exists; the LLM judge is only a fallback for open-ended tasks. Routing was already decided, so grading never affects online behaviour.
> Judge: `external-non-qwen-judge` | sample: 50 tasks
> Judge tokens are priced with the frontier rate of pricing_file; that is an estimate, not the judge model's own tariff.

| Policy | Tasks | Judged | Judge failures | Verified | LLM judged | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | 50 | 0 | 35 | 15 | 90.00% | $0.000279 | $0.000641 | $0.003007 | $0.016304 |
| cascade | 50 | 50 | 0 | 35 | 15 | 88.00% | $0.000081 | $0.000485 | $0.001868 | $0.017779 |
| all_small | 50 | 50 | 0 | 35 | 15 | 82.00% | $0.000025 | $0.000496 | $0.000453 | $0.019307 |

> Judged success comes from the task's deterministic verifier when one exists, otherwise from a strict rubric-based LLM judge. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.

## Threshold sweep (offline replay, no extra API calls)

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.000 | 0% | 82% | $0.001466 | $0.000025 |
| 0.600 | 0% | 82% | $0.001466 | $0.000025 |
| 0.625 | 0% | 82% | $0.001466 | $0.000025 |
| 0.650 | 0% | 82% | $0.001466 | $0.000025 |
| 0.675 | 0% | 82% | $0.001466 | $0.000025 |
| 0.700 | 0% | 82% | $0.001466 | $0.000025 |
| 0.725 | 0% | 82% | $0.001466 | $0.000025 |
| 0.750 | 0% | 82% | $0.001466 | $0.000025 |
| 0.775 | 0% | 82% | $0.001466 | $0.000025 |
| 0.800 | 0% | 82% | $0.001466 | $0.000025 |
| 0.825 | 4% | 84% | $0.002664 | $0.000054 |
| 0.850 | 12% | 84% | $0.005326 | $0.000095 |
| 0.875 | 18% | 88% | $0.007344 | $0.000140 |
| 0.900 | 36% | 92% | $0.013305 | $0.000246 |
| 0.925 | 46% | 90% | $0.014398 | $0.000251 |
| 0.950 | 50% | 90% | $0.014650 | $0.000257 |
| 1.000 | 58% | 90% | $0.016710 | $0.000299 |

> Replayed from the recorded answers, verdicts and costs; the judge is never re-called, so this sweep cannot change any online route.
