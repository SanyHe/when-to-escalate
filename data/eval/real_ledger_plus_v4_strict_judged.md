# Real Ledger (LLM-as-a-Judge)

> Answers are graded by the task's deterministic verifier when one exists; the LLM judge is only a fallback for open-ended tasks. Routing was already decided, so grading never affects online behaviour.
> Judge: `external-non-qwen-judge` | sample: 50 tasks
> Judge tokens are priced with the frontier rate of pricing_file; that is an estimate, not the judge model's own tariff.

| Policy | Tasks | Judged | Judge failures | Verified | LLM judged | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | 50 | 0 | 35 | 15 | 88.00% | $0.000258 | $0.000728 | $0.004428 | $0.020717 |
| cascade | 50 | 50 | 0 | 35 | 15 | 86.00% | $0.000259 | $0.000769 | $0.004147 | $0.021934 |
| all_small | 50 | 50 | 0 | 35 | 15 | 78.00% | $0.000022 | $0.000404 | $0.000615 | $0.014888 |

> Judged success comes from the task's deterministic verifier when one exists, otherwise from a strict rubric-based LLM judge. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.

## Threshold sweep (offline replay, no extra API calls)

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.000 | 0% | 78% | $0.001466 | $0.000022 |
| 0.600 | 0% | 78% | $0.001466 | $0.000022 |
| 0.625 | 0% | 78% | $0.001466 | $0.000022 |
| 0.650 | 0% | 78% | $0.001466 | $0.000022 |
| 0.675 | 0% | 78% | $0.001466 | $0.000022 |
| 0.700 | 0% | 78% | $0.001466 | $0.000022 |
| 0.725 | 0% | 78% | $0.001466 | $0.000022 |
| 0.750 | 0% | 78% | $0.001466 | $0.000022 |
| 0.775 | 0% | 78% | $0.001466 | $0.000022 |
| 0.800 | 0% | 78% | $0.001466 | $0.000022 |
| 0.825 | 4% | 78% | $0.002740 | $0.000036 |
| 0.850 | 12% | 80% | $0.004992 | $0.000072 |
| 0.875 | 18% | 82% | $0.006955 | $0.000098 |
| 0.900 | 36% | 86% | $0.013211 | $0.000223 |
| 0.925 | 46% | 86% | $0.014454 | $0.000224 |
| 0.950 | 50% | 86% | $0.014769 | $0.000232 |
| 1.000 | 58% | 88% | $0.016920 | $0.000275 |

> Replayed from the recorded answers, verdicts and costs; the judge is never re-called, so this sweep cannot change any online route.
