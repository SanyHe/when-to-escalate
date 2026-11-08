# Cascade Ledger (REAL)

> REAL LEDGER: measured against live OpenAI-compatible backends. Do not compare or merge with mock_ledger.json.
> Backends: `qwen-plus` -> `qwen-max`
> Sample: 20 tasks, generated at 2026-11-08T08:47:51.865657+00:00
> Prices: Prices come from the file named in pricing_file. Verify the FX assumption and official prices before quoting cost. (`cascade/configs/pricing.qwen.yaml`)
> Output budget: 1024 completion tokens per call (same for both roles)

| Policy | Tasks | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 20 | $0.005683 | $0.000284 | 100.00% | 0.00% | 6671 ms | 1.000 | 0.00% |
| cascade | 20 | $0.002954 | $0.000148 | 100.00% | 0.00% | 12188 ms | 1.000 | 48.03% |
| all_small | 20 | $0.002962 | $0.000148 | 100.00% | 0.00% | 12346 ms | 1.000 | 47.89% |

> CPST = total cost of successful tasks / successful tasks; retry and escalation spend is included. Real-model cost figures depend on the prices configured in `cascade/configs/pricing.yaml`.
