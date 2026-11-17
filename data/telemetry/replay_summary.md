# Decision Replay (SIMULATED)

> SIMULATED: outcomes, token counts and latencies are synthetic priors, not a model measurement. Prices are illustrative.

| Bucket | Decisions | Escalated | Accepted | Edited | Undone | Failed | Pending | Accept rate | Avg cost | Avg latency |
|---|---|---|---|---|---|---|---|---|---|---|
| B0_sense | 38 | 0 | 12 | 0 | 0 | 0 | 0 | 31.6% | $0.000000 | 16 ms |
| B1_read | 42 | 0 | 26 | 6 | 2 | 7 | 0 | 61.9% | $0.000181 | 785 ms |
| B2_draft | 48 | 8 | 30 | 7 | 1 | 4 | 5 | 69.8% | $0.001316 | 985 ms |
| B3_act_reversible | 37 | 6 | 23 | 2 | 2 | 0 | 10 | 85.2% | $0.000939 | 926 ms |
| B4_act_irreversible | 31 | 0 | 13 | 2 | 0 | 2 | 14 | 76.5% | $0.005636 | 1017 ms |
| B5_background | 44 | 0 | 17 | 1 | 2 | 6 | 17 | 63.0% | $0.000108 | 497 ms |

Deferred by a hard constraint: 32  
Queued for confirmation: 19  
Escalated attempts: 14

## Hard constraint hits

| Override | Decisions |
|---|---|
| `budget:exhausted` | 10 |
| `device:low_battery` | 17 |
| `local_model:unavailable` | 5 |
| `presence:absent` | 14 |
| `sensitivity:local_only` | 14 |

B0 accept rate is not meaningful: sensing decisions are filtered without a model call, so they are reported as `ignored` or accepted.
