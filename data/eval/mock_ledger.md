# Cascade Ledger (MOCK)

> MOCK LEDGER: deterministic mock backend, not measured model output. Replace with real-backend evidence (F2.5) before quoting these numbers.
> Prices: Illustrative example prices; verify before quoting.

| Policy | Tasks | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 100 | $0.235848 | $0.002378 | 98.00% | 0.00% | 824 ms | 1.000 | 0.00% |
| cascade | 100 | $0.118222 | $0.001184 | 99.00% | 29.00% | 660 ms | 1.290 | 49.87% |
| all_small | 100 | $0.011840 | $0.000113 | 93.00% | 0.00% | 394 ms | 1.240 | 94.98% |

> CPST = total cost of successful tasks / successful tasks; retry and escalation spend is included.
