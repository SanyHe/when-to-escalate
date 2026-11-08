# 03 · Evaluation, Ledger and Limits

> Every default number comes from `data/eval/mock_ledger.json` (deterministic mock backend), not from measured model output. The real-backend pilot covers 20 judged tasks and is still not a production conclusion; see section 8.

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

## 8. Real-backend evaluation (F2.5): 20-task pilot

The real path is running: `qwen-plus` (small) → `qwen-max` (frontier) through an OpenAI-compatible endpoint, priced with the official Qwen rates (`cascade/configs/pricing.qwen.yaml`, FX 7.2; small 0.111/0.278, frontier 0.333/1.333 USD / 1M tokens). The sample is 20 tasks spread across the 100-task flow (simple 11 / medium 6 / complex 3), with a shared `max_tokens=1024` for both roles; results live in `data/eval/real_ledger.json` and are never merged with the mock ledger.

### 8.1 Serving-level results (HTTP success)

| Policy | Total cost | CPST | Success | Escalation | Avg latency | Avg attempts | Savings vs frontier |
|---|---|---|---|---|---|---|---|
| `all_frontier` | $0.005683 | $0.000284 | 100% | 0% | 6671 ms | 1.000 | 0% |
| `cascade` | $0.002954 | $0.000148 | 100% | 0% | 12188 ms | 1.000 | **48.03%** |
| `all_small` | $0.002962 | $0.000148 | 100% | 0% | 12346 ms | 1.000 | 47.89% |

How to read it:

- With a shared output budget, cascade/all_small save **~48%** versus all-frontier — strikingly close to the mock's 49.87%. The earlier 5-task pilot showed only 1%–6%, which we now know was small-model verbosity (qwen-plus once emitted 2342 completion tokens on a single task; now capped at 1024).
- **Escalation is 0%**: qwen-plus reported mean token probabilities of 0.80–0.99 (median 0.8958), all above the 0.66 threshold, so cascade degenerates into all_small (the $0.000008 cost gap is just request ordering).
- qwen-max reports a constant confidence of 1.0 — it apparently does not return usable logprobs, so the confidence signal is only trustworthy on qwen-plus.

### 8.2 Judged results (LLM-as-a-judge)

HTTP success is not task success. The offline judge (`cascade/src/judge.py` / `judge_ledger.py`, strict rubric, temperature 0, policy-blind) fails answers that only ask for more information. Judge-side call failures (timeout / rate limit) are counted as `judge_failures` and **excluded from the judged denominator**.

| Policy | Tasks | Judged passes | Judged success | CPST (serving) | CPST (incl. judge) | Failed spend | Judge cost |
|---|---|---|---|---|---|---|---|
| `all_frontier` | 20 (6 judge failures) | 10/14 | 71.4% | $0.000421 | $0.000665 | $0.001810 | $0.002446 |
| `cascade` | 20 | 19/20 | 95.0% | $0.000140 | $0.000427 | $0.000308 | $0.005442 |
| `all_small` | 20 | 19/20 | 95.0% | $0.000141 | $0.000427 | $0.000308 | $0.005437 |

How to read it:

- **The cascade advantage widens under judged success**: all_frontier has 4 genuine quality failures (answers that only ask for more information), pushing its CPST to $0.000421 — 3× cascade's $0.000140. qwen-max answers are terse (median 101 completion tokens vs qwen-plus 545), and terse answers fail the strict rubric more often.
- The only cascade / all_small failure is `task_0066`, where the budget constraint really is violated (transport overspend) — a legitimate verdict.
- Judge cost ($0.0024–$0.0054) again exceeds serving cost; with judging folded in, all_frontier stays at $0.000665 and the ranking holds. **Judging is an evaluation cost, not an online CPST input.**

### 8.3 Reproduce

```bash
# Real three-policy run (needs DASHSCOPE_API_KEY or CASCADE_SMALL_* / CASCADE_FRONTIER_*)
python3 cascade/src/real_eval.py --limit 20 --max-tokens 1024 \
    --pricing cascade/configs/pricing.qwen.yaml
# Offline judging (reads the real ledger, does not regenerate answers)
python3 cascade/src/judge_ledger.py --ledger data/eval/real_ledger.json
```

Outputs: `data/eval/real_ledger.{json,md}`, `data/eval/real_ledger_judged.{json,md}`.

### 8.4 Required before any production claim

1. Scale to 50–100 tasks and report by difficulty; complex currently has only 3 tasks, so the hard tier is not credible.
2. Judge with a non-qwen-max model (the current judge shares its family with all_frontier's answers — self-preference risk) or cross-check with two judges.
3. Replace mean token probability with top-1/top-2 logprob margin or self-consistency, and recalibrate the threshold on the real distribution — at 0.66 the escalation rate is 0%, so confidence currently does no filtering.
4. Add retries and alerting to the judge itself: a 6/20 judge-failure rate (all_frontier column) shows the judge channel is not yet stable.

## 9. Known limits

- Mock `success` is a probability event, not a quality label; a real evaluation needs task-level rubrics or human annotation.
- Confidence is a rule plus stable jitter; the real pilot confirmed qwen-plus mean token probabilities (0.80–0.99) all sit above the 0.66 threshold, so escalation is 0% and the threshold must be recalibrated before production.
- Small-model output length dominates real cost; the real eval pins `max_tokens=1024` for both roles, and every policy comparison must fix the output budget first.
- There are two price sets (illustrative mock and official Qwen); every cost claim must name the price file and FX.
- 20 real tasks are a pilot: the directional signals (~48% savings with a shared budget, 3× CPST gap under judged success) are quotable, but the absolute numbers are not a production conclusion; the 100 mock tasks only validate the ledger and interactions.
- The judge has its own bias and cost (judging costs more than serving), and the current judge shares its family with the frontier model under test; report `CPST (incl. judge)` separately from serving CPST and count judge-side failures separately.
