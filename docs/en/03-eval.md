# 03 · Evaluation, Ledger and Limits

> Every default number comes from `data/eval/mock_ledger.json` (deterministic mock backend), not from measured model output. The real-backend evaluation (F2.5) is **blocked**; see section 8.

## 1. Questions

The evaluation answers three questions:

1. On the **same task flow**, how do the three architectures differ in total cost, CPST, success, escalation and latency?
2. Does the cascade escalate on the tasks that actually need it, with a traceable reason?
3. Do the browser panel's numbers exactly match the local Python ledger?

Out of scope:

- real-model quality differences (needs task-level rubrics or human labels);
- gains from a learned router;
- long-run cost distributions under production traffic.

## 2. Setup

| Item | Value |
|---|---|
| Task flow | 100 synthetic tasks, fixed seed, `simple/medium/complex = 50/30/20` |
| Prices | Example: small 0.15/0.60, frontier 3.00/12.00 USD / 1M tokens |
| Threshold | 0.66 |
| Small-model retry cap (all_small) | 2 |
| Backend | Deterministic `MockBackend` (not a real model) |
| Success | model response `success = true`; task success = any attempt succeeded |

## 3. Metric definitions

| Metric | Definition |
|---|---|
| `total_cost_usd` | sum of every attempt's cost under the policy |
| `cpst_usd` | total cost of successful tasks ÷ successful tasks |
| `success_rate` | successful tasks ÷ all tasks |
| `escalation_rate` | tasks with at least one escalation ÷ all tasks |
| `avg_latency_ms` | mean over tasks of the summed attempt latency |
| `avg_attempts` | mean number of attempts per task |
| `failed_cost_usd` | money spent on tasks that ultimately failed |
| `savings_vs_frontier` | `1 - policy total cost / all-frontier total cost` |

Important: CPST's numerator includes only successful tasks, but those tasks include retry and escalation spend. Failed spend is reported separately as `failed_cost_usd`; it does not disappear from the denominator.

## 4. Mock results

| Policy | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Failed spend | Savings |
|---|---|---|---|---|---|---|---|---|
| `all_frontier` | $0.235848 | $0.002378 | 98% | 0% | 824 ms | 1.00 | $0.002778 | 0% |
| `cascade` | $0.118222 | $0.001184 | 99% | 29% | 660 ms | 1.29 | $0.001031 | **49.87%** |
| `all_small` | $0.011840 | $0.000113 | 93% | 0% | 394 ms | 1.24 | $0.001361 | 94.98% |

How to read it:

- The cascade is **not a cheaper all-frontier**: it escalates 29% of tasks, succeeds on 99%, and cuts total cost to roughly half.
- The all-small policy is cheapest per call but succeeds on 93%; its failed spend ($0.001361) exceeds the cascade's entire failed spend ($0.001031). A cheap unit price is not a cheap successful task.
- All-frontier success is 98%, not 100%: the mock backend fails sometimes, and failure still costs money. That is exactly why CPST includes failure spend.
- Cost and latency do not move together: all-small is fastest on average, cascade is in the middle, all-frontier is slowest; escalation pays a latency penalty on the tail.

> Everything above is MOCK. Any external citation must carry the mock label and the illustrative-pricing caveat.

## 5. Python ↔ browser consistency

The panel does not ship a pre-rendered table; it recomputes from raw attempts:

1. `replay.py` writes each task's raw small/frontier attempts into `web/data/ledger.json`;
2. `web/js/metrics.js` applies the same rules as `engine.py` / `pricing.py`;
3. `node cascade/tests/verify_web_metrics.js` compares seven metrics and exits non-zero on drift.

Output at defaults:

```
ledger mode: mock | tasks: 100
  all_frontier OK cost=0.235848 cpst=0.002378 success=98.0% escalation=0.0% savings=0.0%
  cascade      OK cost=0.118222 cpst=0.001184 success=99.0% escalation=29.0% savings=49.9%
  all_small    OK cost=0.011840 cpst=0.000113 success=93.0% escalation=0.0% savings=95.0%
web metrics match the Python ledger
```

## 6. Reproduce

```bash
python3 cascade/src/gen_tasks.py
python3 cascade/src/replay.py
python3 -m pytest cascade/tests/ -q
node cascade/tests/verify_web_metrics.js
```

Outputs:

- `data/synthetic/seed_tasks.jsonl`
- `data/eval/mock_ledger.json` / `.md`
- `web/data/ledger.json`

## 7. Failure cases and traceability

- Cascade fallback path: small fails → frontier attempt; `reason` starts with `fallback`.
- Cascade quality path: small succeeds but confidence is below the threshold → frontier attempt; `reason` starts with `quality check`.
- Both paths are forced with scripted backends in `test_engine.py`, so they cannot pass by luck.
- `export_trace()` produces a chain such as `task_0001 (cascade) -> small ... -> frontier ...` for evidence.

## 8. Real-backend evaluation (F2.5): Blocked

F2.5 requires a real small model (vLLM) and a real frontier endpoint, with results reported separately from mock. The current environment lacks:

- a GPU host or reachable vLLM service;
- frontier endpoint credentials, which must be injected through environment variables.

F2.5 is therefore **blocked**, not passing. After unblocking:

1. export `CASCADE_SMALL_BASE_URL` / `CASCADE_FRONTIER_*`;
2. run all three policies on the real backends and record success, latency, tokens and failure reasons;
3. save the real ledger as `data/eval/real_ledger.json` and present it separately from mock;
4. only then may the project claim production cascade economics.

## 9. Known limits

- Mock `success` is a probability event, not a quality label; a real evaluation needs task-level rubrics or human annotation.
- Confidence is a rule plus stable jitter, not a calibrated model signal; replace it with logprob margin, self-consistency or a learned classifier in production.
- Prices are examples; replace them with current official prices before quoting real costs.
- 100 tasks validate the ledger and interactions only; production conclusions need larger and out-of-distribution samples.
