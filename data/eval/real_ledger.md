# Cascade Ledger (REAL)

> REAL LEDGER: measured against live OpenAI-compatible backends. Do not compare or merge with mock_ledger.json.
> Backends: `qwen-plus` -> `qwen-max`
> Sample: 50 tasks, generated at 2026-11-08T14:17:43.351822+00:00
> Prices: Prices come from the file named in pricing_file. Verify the FX assumption and official prices before quoting cost. (`cascade/configs/pricing.qwen.yaml`)
> Output budget: 1024 completion tokens per call (same for both roles)

| Policy | Tasks | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |
|---|---|---|---|---|---|---|---|---|
| all_frontier | 50 | $0.019143 | $0.000383 | 100.00% | 0.00% | 8711 ms | 1.000 | 0.00% |
| cascade | 50 | $0.015784 | $0.000316 | 100.00% | 34.00% | 16199 ms | 1.340 | 17.55% |
| all_small | 50 | $0.007486 | $0.000150 | 100.00% | 0.00% | 12427 ms | 1.000 | 60.89% |

> CPST = total cost of successful tasks / successful tasks; retry and escalation spend is included. Real-model cost figures depend on the prices configured in `cascade/configs/pricing.qwen.yaml`.
