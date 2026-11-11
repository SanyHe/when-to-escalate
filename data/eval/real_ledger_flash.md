# Cascade Ledger (REAL)

> REAL LEDGER: measured against live OpenAI-compatible backends. Do not compare or merge with mock_ledger.json.
> Backends: `qwen-flash` -> `qwen-max`
> Sample: 50 tasks, generated at 2026-11-11T12:37:42.375616+00:00
> Prices: Prices come from the file named in pricing_file. Verify the FX assumption and official prices before quoting cost. (`cascade/configs/pricing.qwen-flash.yaml`)
> Output budget: 1024 completion tokens per call (same for both roles)

| Policy | Tasks | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | $0.018866 | $0.000377 | 100.00% | 0.00% | 8563 ms | 1.000 | 0.00% |
| cascade | 50 | $0.012931 | $0.000259 | 100.00% | 56.00% | 6332 ms | 1.560 | 31.46% |
| all_small | 50 | $0.000951 | $0.000019 | 100.00% | 0.00% | 1118 ms | 1.000 | 94.96% |

> CPST = total cost of successful tasks / successful tasks; retry and escalation spend is included. Real-model cost figures depend on the prices configured in `cascade/configs/pricing.qwen-flash.yaml`.
