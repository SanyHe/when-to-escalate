# Cascade Ledger (REAL)

> REAL LEDGER: measured against live OpenAI-compatible backends. Do not compare or merge with mock_ledger.json.
> Backends: `qwen-plus` -> `qwen-max`
> Sample: 50 tasks, generated at 2026-11-18T15:22:11.066588+00:00
> Prices: Prices come from the file named in pricing_file. Verify the FX assumption and official prices before quoting cost. (`cascade/configs/pricing.qwen.yaml`)
> Output budget: 1024 completion tokens per call (same for both roles)

| Policy | Tasks | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | $0.015675 | $0.000313 | 100.00% | 0.00% | 7353 ms | 1.000 | 0.00% |
| cascade | 50 | $0.005587 | $0.000112 | 100.00% | 16.00% | 4274 ms | 1.160 | 64.36% |
| all_small | 50 | $0.001470 | $0.000029 | 100.00% | 0.00% | 2433 ms | 1.000 | 90.62% |

> CPST = total cost of successful tasks / successful tasks; retry and escalation spend is included. Real-model cost figures depend on the prices configured in `cascade/configs/pricing.qwen.yaml`.
