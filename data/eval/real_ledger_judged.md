# Real Ledger (LLM-as-a-Judge)

> Answers are judged offline with a strict rubric; routing was already decided, so the judge never affects online behaviour.
> Judge: `qwen-max` | sample: 20 tasks

| Policy | Tasks | Judged | Judge failures | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 20 | 14 | 6 | 71.43% | $0.000421 | $0.000665 | $0.000325 | $0.002446 |
| cascade | 20 | 20 | 0 | 95.00% | $0.000140 | $0.000427 | $0.000288 | $0.005442 |
| all_small | 20 | 20 | 0 | 95.00% | $0.000141 | $0.000427 | $0.000288 | $0.005437 |

> Judged success comes from a strict rubric-based judge, not HTTP success. Judge failures are judge-side infrastructure errors (timeout / rate limit), not quality verdicts, so they are excluded from the success denominator.
