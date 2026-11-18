# Cascade Ledger (REAL)

> REAL LEDGER: measured against live OpenAI-compatible backends. Do not compare or merge with mock_ledger.json.
> Backends: `qwen-plus` -> `qwen-max`
> Sample: 50 tasks, generated at 2026-11-18T05:25:03.683184+00:00
> Prices: Prices come from the file named in pricing_file. Verify the FX assumption and official prices before quoting cost. (`cascade/configs/pricing.qwen.yaml`)
> Output budget: 1024 completion tokens per call (same for both roles)

| Policy | Tasks | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | $0.015219 | $0.000304 | 100.00% | 0.00% | 6818 ms | 1.000 | 0.00% |
| cascade | 50 | $0.005153 | $0.000103 | 100.00% | 12.00% | 5313 ms | 1.120 | 66.14% |
| all_small | 50 | $0.001461 | $0.000029 | 100.00% | 0.00% | 5916 ms | 1.040 | 90.40% |

> CPST = total cost of successful tasks / successful tasks; retry and escalation spend is included. Real-model cost figures depend on the prices configured in `cascade/configs/pricing.qwen.yaml`.
