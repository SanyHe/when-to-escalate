# Cascade Ledger (REAL)

> REAL LEDGER: measured against live OpenAI-compatible backends. Do not compare or merge with mock_ledger.json.
> Backends: `qwen-plus` -> `qwen-max`
> Sample: 50 tasks, generated at 2026-11-11T11:41:59.232488+00:00
> Prices: Prices come from the file named in pricing_file. Verify the FX assumption and official prices before quoting cost. (`cascade/configs/pricing.qwen.yaml`)
> Output budget: 1024 completion tokens per call (same for both roles)

| Policy | Tasks | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | $0.019848 | $0.000397 | 100.00% | 0.00% | 8891 ms | 1.000 | 0.00% |
| cascade | 50 | $0.006939 | $0.000139 | 100.00% | 34.00% | 5644 ms | 1.340 | 65.04% |
| all_small | 50 | $0.001768 | $0.000035 | 100.00% | 0.00% | 2902 ms | 1.000 | 91.09% |

> CPST = total cost of successful tasks / successful tasks; retry and escalation spend is included. Real-model cost figures depend on the prices configured in `cascade/configs/pricing.qwen.yaml`.
