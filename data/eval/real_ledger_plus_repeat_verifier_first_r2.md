# Cascade Ledger (REAL)

> REAL LEDGER: measured against live OpenAI-compatible backends. Do not compare or merge with mock_ledger.json.
> Backends: `qwen-plus` -> `qwen-max`
> Sample: 50 tasks, generated at 2026-11-19T14:43:06.143949+00:00
> Prices: Prices come from the file named in pricing_file. Verify the FX assumption and official prices before quoting cost. (`cascade/configs/pricing.qwen.yaml`)
> Output budget: 1024 completion tokens per call (same for both roles)

| Policy | Tasks | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | $0.015206 | $0.000304 | 100.00% | 0.00% | 6910 ms | 1.000 | 0.00% |
| cascade | 50 | $0.005735 | $0.000115 | 100.00% | 16.00% | 4484 ms | 1.160 | 62.28% |
| all_small | 50 | $0.001463 | $0.000029 | 100.00% | 0.00% | 2392 ms | 1.000 | 90.38% |

> CPST = total cost of successful tasks / successful tasks; retry and escalation spend is included. Real-model cost figures depend on the prices configured in `cascade/configs/pricing.qwen.yaml`.
