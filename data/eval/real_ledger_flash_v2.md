# Cascade Ledger (REAL)

> REAL LEDGER: measured against live OpenAI-compatible backends. Do not compare or merge with mock_ledger.json.
> Backends: `qwen-flash` -> `qwen-max`
> Sample: 50 tasks, generated at 2026-11-17T16:31:19.769807+00:00
> Prices: Prices come from the file named in pricing_file. Verify the FX assumption and official prices before quoting cost. (`cascade/configs/pricing.qwen-flash.yaml`)
> Output budget: 1024 completion tokens per call (same for both roles)

| Policy | Tasks | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | $0.015796 | $0.000316 | 100.00% | 0.00% | 7150 ms | 1.000 | 0.00% |
| cascade | 50 | $0.008107 | $0.000162 | 100.00% | 28.00% | 4470 ms | 1.280 | 48.68% |
| all_small | 50 | $0.000665 | $0.000013 | 100.00% | 0.00% | 935 ms | 1.000 | 95.79% |

> CPST = total cost of successful tasks / successful tasks; retry and escalation spend is included. Real-model cost figures depend on the prices configured in `cascade/configs/pricing.qwen-flash.yaml`.
