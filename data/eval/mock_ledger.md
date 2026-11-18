# Cascade Ledger (MOCK)

> MOCK LEDGER: deterministic mock backend, not measured model output. Replace with real-backend evidence (F2.5) before quoting these numbers.
> Prices: Illustrative example prices; verify before quoting.

| Policy | Tasks | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 100 | $0.234234 | $0.002375 | 97.00% | 0.00% | 824 ms | 1.000 | 0.00% |
| cascade | 100 | $0.122186 | $0.001224 | 99.00% | 30.00% | 673 ms | 1.300 | 47.84% |
| all_small | 100 | $0.011843 | $0.000113 | 92.00% | 0.00% | 399 ms | 1.250 | 94.94% |

> CPST = total cost of successful tasks / successful tasks; retry and escalation spend is included.
