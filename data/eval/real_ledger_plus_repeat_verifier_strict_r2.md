# Cascade Ledger (REAL)

> REAL LEDGER: measured against live OpenAI-compatible backends. Do not compare or merge with mock_ledger.json.
> Backends: `qwen-plus` -> `qwen-max`
> Sample: 50 tasks, generated at 2026-11-19T12:48:12.627885+00:00
> Prices: Prices come from the file named in pricing_file. Verify the FX assumption and official prices before quoting cost. (`cascade/configs/pricing.qwen.yaml`)
> Output budget: 1024 completion tokens per call (same for both roles)

| Policy | Tasks | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | $0.015200 | $0.000304 | 100.00% | 0.00% | 7034 ms | 1.000 | 0.00% |
| cascade | 50 | $0.015104 | $0.000302 | 100.00% | 40.00% | 8623 ms | 1.400 | 0.63% |
| all_small | 50 | $0.001476 | $0.000030 | 100.00% | 0.00% | 2492 ms | 1.000 | 90.29% |

> CPST = total cost of successful tasks / successful tasks; retry and escalation spend is included. Real-model cost figures depend on the prices configured in `cascade/configs/pricing.qwen.yaml`.
