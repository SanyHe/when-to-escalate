# Real Ledger (LLM-as-a-Judge)

> Answers are graded by the task's deterministic verifier when one exists; the LLM judge is only a fallback for open-ended tasks. Routing was already decided, so grading never affects online behaviour.
> Judge: `external-non-qwen-judge` | sample: 50 tasks
> Judge tokens are priced with the frontier rate of pricing_file; that is an estimate, not the judge model's own tariff.

| Policy | Tasks | Judged | Judge failures | Verified | LLM judged | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | 50 | 0 | 35 | 15 | 96.00% | $0.000293 | $0.000785 | $0.001718 | $0.023588 |
| cascade | 50 | 50 | 0 | 35 | 15 | 84.00% | $0.000135 | $0.000515 | $0.002456 | $0.015968 |
| all_small | 50 | 50 | 0 | 35 | 15 | 76.00% | $0.000012 | $0.000592 | $0.000212 | $0.022053 |

> Judged success comes from the task's deterministic verifier when one exists, otherwise from a strict rubric-based LLM judge. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.

## Threshold sweep (offline replay, no extra API calls)

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.000 | 0% | 76% | $0.000665 | $0.000012 |
| 0.600 | 0% | 76% | $0.000665 | $0.000012 |
| 0.625 | 0% | 76% | $0.000665 | $0.000012 |
| 0.650 | 0% | 76% | $0.000665 | $0.000012 |
| 0.675 | 0% | 76% | $0.000665 | $0.000012 |
| 0.700 | 0% | 76% | $0.000665 | $0.000012 |
| 0.725 | 0% | 76% | $0.000665 | $0.000012 |
| 0.750 | 2% | 74% | $0.001527 | $0.000011 |
| 0.775 | 6% | 78% | $0.002404 | $0.000034 |
| 0.800 | 10% | 80% | $0.003938 | $0.000073 |
| 0.825 | 14% | 82% | $0.005320 | $0.000105 |
| 0.850 | 36% | 92% | $0.011560 | $0.000212 |
| 0.875 | 40% | 92% | $0.013176 | $0.000248 |
| 0.900 | 42% | 92% | $0.013984 | $0.000265 |
| 0.925 | 44% | 92% | $0.013997 | $0.000265 |
| 0.950 | 44% | 92% | $0.013997 | $0.000265 |
| 1.000 | 68% | 96% | $0.016220 | $0.000301 |

> Replayed from the recorded answers, verdicts and costs; the judge is never re-called, so this sweep cannot change any online route.
