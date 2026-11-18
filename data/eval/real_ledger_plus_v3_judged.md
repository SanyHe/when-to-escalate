# Real Ledger (LLM-as-a-Judge)

> Answers are graded by the task's deterministic verifier when one exists; the LLM judge is only a fallback for open-ended tasks. Routing was already decided, so grading never affects online behaviour.
> Judge: `external-non-qwen-judge` | sample: 50 tasks
> Judge tokens are priced with the frontier rate of pricing_file; that is an estimate, not the judge model's own tariff.

| Policy | Tasks | Judged | Judge failures | Verified | LLM judged | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | 50 | 0 | 35 | 15 | 96.00% | $0.000292 | $0.000991 | $0.001650 | $0.033530 |
| cascade | 50 | 50 | 0 | 35 | 15 | 86.00% | $0.000087 | $0.000695 | $0.001860 | $0.026171 |
| all_small | 50 | 50 | 0 | 35 | 15 | 80.00% | $0.000023 | $0.000509 | $0.000536 | $0.019440 |

> Judged success comes from the task's deterministic verifier when one exists, otherwise from a strict rubric-based LLM judge. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.

## Threshold sweep (offline replay, no extra API calls)

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.000 | 0% | 80% | $0.001470 | $0.000023 |
| 0.600 | 0% | 80% | $0.001470 | $0.000023 |
| 0.625 | 0% | 80% | $0.001470 | $0.000023 |
| 0.650 | 0% | 80% | $0.001470 | $0.000023 |
| 0.675 | 0% | 80% | $0.001470 | $0.000023 |
| 0.700 | 0% | 80% | $0.001470 | $0.000023 |
| 0.725 | 0% | 80% | $0.001470 | $0.000023 |
| 0.750 | 0% | 80% | $0.001470 | $0.000023 |
| 0.775 | 0% | 80% | $0.001470 | $0.000023 |
| 0.800 | 0% | 80% | $0.001470 | $0.000023 |
| 0.825 | 4% | 82% | $0.002547 | $0.000051 |
| 0.850 | 12% | 86% | $0.005283 | $0.000115 |
| 0.875 | 18% | 88% | $0.007347 | $0.000143 |
| 0.900 | 36% | 94% | $0.013388 | $0.000267 |
| 0.925 | 46% | 94% | $0.014397 | $0.000268 |
| 0.950 | 50% | 94% | $0.014775 | $0.000276 |
| 1.000 | 58% | 96% | $0.016837 | $0.000313 |

> Replayed from the recorded answers, verdicts and costs; the judge is never re-called, so this sweep cannot change any online route.
