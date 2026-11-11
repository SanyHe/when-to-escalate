# 03 · Evaluation, Ledger and Limits

> Every default number comes from `data/eval/mock_ledger.json` (deterministic mock backend), not from measured model output. Several 50-task stratified real-backend evaluations now exist (non-Qwen judge plus threshold sweeps): the baseline is negative, compressing qwen-plus output produces a narrow win, and switching to the cheaper qwen-flash loses the matched-success saving because answer quality falls; see section 8. Real data is not a production conclusion.

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

## 8. Real-backend evaluation (F2.5): 50-task stratified sample

Real path: `qwen-plus` (small, with logprobs) → `qwen-max` (frontier) through an OpenAI-compatible endpoint (Alibaba Bailian), priced with official Qwen rates (`cascade/configs/pricing.qwen.yaml`, FX 7.2; small 0.111/0.278, frontier 0.333/1.333 USD / 1M tokens). The sample is **stratified by difficulty**: 50 tasks (simple 25 / medium 15 / complex 10), shared `max_tokens=1024`, threshold 0.85. Results live in `data/eval/real_ledger.json` and are never merged with the mock ledger.

> The earlier 20-task pilot (even spacing, threshold 0.66) is kept as a historical reference at the end of this section.

### 8.1 Serving-level results (HTTP success)

| Policy | Total cost | CPST | Success | Escalation | Savings vs frontier |
|---|---|---|---|---|---|
| `all_frontier` | $0.019143 | $0.000383 | 100% | 0% | 0% |
| `cascade` | $0.015784 | $0.000316 | 100% | 34% | **17.55%** |
| `all_small` | $0.007486 | $0.000150 | 100% | 0% | 60.89% |

All three policies report 100% HTTP success: the Bailian channel had no timeouts or rate limits in this round, so **HTTP success cannot distinguish quality at all** — judging is mandatory.

### 8.2 Judged results (LLM-as-a-judge)

The judge is an **external non-Qwen model** (not the qwen-max under test; its name is internal and kept out of the public repo — set it with `CASCADE_JUDGE_MODEL` and record a neutral `CASCADE_JUDGE_LABEL`), strict rubric, temperature 0, policy-blind.

| Policy | Judged passes | Judged success | CPST (serving) | CPST (incl. judge) | Judge cost |
|---|---|---|---|---|---|
| `all_frontier` | 39/50 | 78% | $0.000263 | $0.001340 | $0.042023 |
| `cascade` | 25/50 | 50% | $0.000382 | $0.001743 | $0.034019 |
| `all_small` | 14/50 | 28% | $0.000126 | $0.002542 | $0.033827 |

Re-judging the same answers with the same judge moved `all_frontier` 82%→78% and `all_small` 26%→28% (two tasks each): at n=50, differences of ~5pp are not stable. Every derived number in this section uses the verdict file on disk.

### 8.3 Threshold sweep: no operating point beats all-frontier on this sample

Offline replay over recorded answers, verdicts and costs (`judge_ledger.py --sweep-only`, **zero model calls**):

| Threshold | Escalation | Judged success | Total cost | CPST |
|---|---|---|---|---|
| 0.66 (mock default) | 0% | 28% | $0.007486 | $0.000126 |
| 0.85 (this run) | 34% | 50% | $0.015950 | $0.000351 |
| 0.90 | 74% | 72% | $0.023331 | $0.000407 |
| 0.925 | 96% | 80% | $0.024797 | $0.000380 |
| 0.95 | 98% | 78% | $0.025682 | $0.000382 |
| — `all_frontier` | 0% | 78% | $0.019143 | **$0.000263** |

The conclusion is negative, and it matters:

- **No threshold delivers both high success and low cost.** At ≤0.80 you spend only $0.007486 but succeed on 28%; at ≥0.925 success reaches 80%, on par with all-frontier's 78%, yet total spend is **29.5% higher** than going straight to the frontier ($0.024797 vs $0.019143; CPST $0.000380 vs $0.000263).
- **Mean token probability has no routing power.** It does not identify the tasks where the frontier would rescue a small-model failure: once escalated, the answer is the frontier's answer, so success caps at 78%, while most non-escalated tasks are quality failures. The cascade here is just "all-small, or all-frontier plus overhead".
- **Some failures cannot be fixed by a stronger model.** 17 of the 50 prompts (34%) lack required input (live weather, meeting minutes/weekly-report bodies); no model can produce correct content from the prompt alone. These tasks depress all three policies and explain why the frontier only reaches 78%.
- F2.5 therefore **cannot be marked passing**: the cost-saving hypothesis does not hold on this real sample with this confidence signal.

### 8.4 Three judge pitfalls and mitigations

1. **Truncation scored as quality failure**: a judge reply cut off by `max_tokens` returned empty content and the old code failed the answer. Now "no JSON" is a **judge fault** (`judge_failed`), retried, and excluded from the denominator if it persists.
2. **Rubric rewarded fabrication**: under the old rubric, a small-model answer that invented meeting minutes passed while the frontier answering honestly ("the material is missing") failed, inverting the first run (small 46% > cascade 40% > frontier 28%). The rubric now states that any date, figure or minutes content the task does not supply is unsupported, fabrication must fail, and clearly flagging missing input while offering next steps passes.
3. **Judge noise**: re-judging the same answers moved a policy by 2/50 tasks; differences around 5pp at n=50 are not stable, so operating points need both cost-structure checks and larger-sample confirmation.

### 8.5 Reproduce

```bash
# Real three policies (needs DASHSCOPE_API_KEY)
python3 cascade/src/real_eval.py --limit 50 --max-tokens 1024 --threshold 0.85 \
    --small-model qwen-plus --frontier-model qwen-max \
    --pricing cascade/configs/pricing.qwen.yaml
# Offline judging (non-Qwen judge; model name via env, neutral label for public artifacts)
CASCADE_JUDGE_MODEL=<judge-model> CASCADE_JUDGE_LABEL=external-non-qwen-judge \
    python3 cascade/src/judge_ledger.py --ledger data/eval/real_ledger.json
# Rebuild only the threshold sweep from stored verdicts, zero API calls
python3 cascade/src/judge_ledger.py --ledger data/eval/real_ledger_judged.json --sweep-only
# Learned-router ceiling, zero API calls
python3 cascade/src/router_ceiling.py
# Break-even inequality and lever scenarios (brevity, price), zero API calls
python3 cascade/src/economics.py
# Re-run with a brevity instruction (separate ledger; never overwrite baseline)
python3 cascade/src/real_eval.py --limit 50 --max-tokens 1024 --threshold 0.85 \
    --small-model qwen-plus --frontier-model qwen-max \
    --small-system-prompt "Be brief: answer in at most 120 words. Do not restate the question or add preamble." \
    --pricing cascade/configs/pricing.qwen.yaml \
    --out data/eval/real_ledger_brief.json --md-out data/eval/real_ledger_brief.md
# Bailian qwen-flash at official list prices; every other setting is unchanged
python3 cascade/src/real_eval.py --limit 50 --max-tokens 1024 --threshold 0.85 \
    --small-model qwen-flash --frontier-model qwen-max \
    --small-system-prompt "Be brief: answer in at most 120 words. Do not restate the question or add preamble." \
    --pricing cascade/configs/pricing.qwen-flash.yaml \
    --out data/eval/real_ledger_flash.json --md-out data/eval/real_ledger_flash.md
CASCADE_JUDGE_MODEL=<judge-model> CASCADE_JUDGE_LABEL=external-non-qwen-judge \
    python3 cascade/src/judge_ledger.py --ledger data/eval/real_ledger_flash.json \
    --out data/eval/real_ledger_flash_judged.json \
    --md-out data/eval/real_ledger_flash_judged.md
python3 cascade/src/economics.py --ledger data/eval/real_ledger_flash.json \
    --judged data/eval/real_ledger_flash_judged.json \
    --pricing cascade/configs/pricing.qwen-flash.yaml \
    --out data/eval/economics_flash.json
```

Outputs: `data/eval/real_ledger*.{json,md}`, `data/eval/router_ceiling.json`, `data/eval/economics*.json`. Each real run uses separate files and is never merged with mock or another real ledger.

### 8.6 Learned-router ceiling (zero API cost)

A lightweight router is trained on the existing 50 labels (`cascade/src/router_ceiling.py`: logistic regression, stratified 5-fold CV; features: difficulty, missing-input tag, prompt length, reported confidence, output length) to answer "would a better router rescue this?". No model is called.

| Policy | Judged success | Total spend (50 tasks) | CPST |
|---|---|---|---|
| `all_frontier` | 78% | $0.019143 | $0.000263 |
| **oracle (perfect router)** | 86% | **$0.015005** | $0.000302 |
| Learned router (all features, AUC 0.895) | 80% | $0.019347 | $0.000292 |
| Confidence only (AUC 0.683) | 78% | $0.0191 | $0.000382 |
| Difficulty only (AUC 0.676) | 78% | $0.0191 | $0.000382 |

- **AUC 0.895 is an illusion.** To operate at 78% success, the confidence-only and difficulty-only routers must escalate **98%–100%** of tasks, which is "all-frontier plus a wasted small call on every task": 39% more total spend under the previous verdict pass and about break-even under this one. A high AUC does not imply savings; the escalation rate does.
- **Even a perfect router saves only 21.6% of total spend**, and it needs to know in advance whether the small model would pass — exactly the unpredictable part.
- **The arithmetic cause**: the small model costs $0.007486 across all 50 tasks; 10 of the 14 it passes are also passed by the frontier, leaving 4 tasks only the small model handles, so at most ~$0.005 of frontier calls can be avoided — a net loss. A cascade needs a **large set of tasks only the small model can handle**.
- This tightens the 8.3 conclusion: the bottleneck is **not the routing signal but the price gap, output length and task mix**. A better router does not fix it.
- Metric caveat: CPST is not comparable across success rates — escalating nothing has the lowest CPST because only easy tasks count as successes. The table therefore also reports total spend at **matched success (≥78%)**.

### 8.7 The break-even inequality (zero API cost)

A fail-then-escalate cascade pays `S + F_fail` while all-frontier pays `F`, so the cascade wins exactly when

```
S / F  <  F_pass / F
```

The left side is the small model's **effective cost ratio**; the right side is the share of frontier spend sitting on tasks the small model would have passed, i.e. all the money escalation can avoid. That share is also the ceiling: **even a free small model cannot save more than it**.

Re-computed from the measured tokens and verdicts of the 50-task run (`cascade/src/economics.py`; no model is called):

| Lever | Effective cost ratio `S/F` | Cascade vs all-frontier | Oracle bound |
|---|---|---|---|
| Baseline (measured) | 0.391 | **−8.6%** | +21.6% |
| Small output ×0.75 | 0.296 | +0.9% | +31.2% |
| **Small output ×0.50** | **0.200** | **+10.5%** | +40.7% |
| Small price ×0.50 | 0.196 | +10.9% | +41.2% |
| Small price ×0.25 | 0.098 | +20.7% | +50.9% |
| Self-hosted small (×0.10) | 0.039 | +26.6% | +56.8% |
| Output ×0.50 + price ×0.50 | 0.100 | +20.5% | +50.7% |

- **0.391 > the 0.305 avoidable share today**; the 0.086 gap is exactly the −8.6%.
- **98% of small-model spend is output tokens**: 26,304 output tokens for $0.00731 versus $0.00017 of input (31 prompt tokens on average). Output length is therefore the most direct lever.
- **The 0.305 avoidable share is set by the task mix** (only 14/50 tasks pass on the small model). A free small model still saves at most 30.5%; growing the win needs more tasks that only the small model can handle.
- The +21.6% oracle matches the 21.6% from 8.6 — two independent computations cross-check each other.

### 8.8 Measured: compressing small-model answers to 120 words flips the sign

Same 50 tasks, same threshold (0.85), same model pair; the only change is one system instruction on the small model (`--small-system-prompt`):

| Metric | Baseline (no limit) | Brief (≤120 words) |
|---|---|---|
| Small-model output (avg) | 526 tokens | **104 tokens** |
| `all_small` judged success | 28% | **44%** |
| `cascade` (threshold 0.85) judged success | 50% | **64%** |
| `all_frontier` judged success | 78% | 78% |
| Small-model total spend | $0.007486 | **$0.001768** |
| Effective cost ratio `S/F` | 0.391 | **0.089** |
| Cheapest point at ~80% success | $0.024797 (threshold 0.925) | **$0.018454** (threshold 0.90) |
| That point vs all-frontier ($0.019143 / $0.019848) | **+29.5%** | **−7.0%** |

- One sentence cuts small-model spend to 24% and pushes `S/F` from 0.391 to 0.089, below the 0.305 threshold from 8.7: the cascade goes from loss to profit.
- Quality did not drop, it rose: `all_small` 28%→44%, `cascade` 50%→64%. Shorter answers pad less and fabricate less, so they clear the anti-fabrication rubric more often.
- At threshold 0.925 success is 84% for $0.018985: 4.3% cheaper than all-frontier while 6pp more successful.
- This is a narrow win, not a rout: a perfect failure signal would save 47.3% (`economics.py`, same data), so the 4–7% realised is limited by signal quality. CPST at that point is roughly level with all-frontier ($0.000286 vs $0.000280).
- Limits: one 50-task run and one judging pass, and re-judging already shifts verdicts by ±2 tasks, so the 4–7% magnitude needs a larger sample; the sign flip itself follows from the cost structure (output length), not from verdict noise.

### 8.9 Measured: Bailian qwen-flash at official list prices

Same 50 task IDs, brevity instruction, threshold 0.85 and `max_tokens=1024`; only the small model changes from qwen-plus to qwen-flash, with qwen-max as the frontier. Serving costs use `cascade/configs/pricing.qwen-flash.yaml`: Beijing-region standard real-time list prices, CNY 0.15/1.5 per 1M input/output tokens for flash in the ≤128K-input tier and CNY 2.4/9.6 for qwen-max, converted at 7.2 CNY/USD. Cache, Batch and free quotas are excluded. The largest prompt in this run was 68 tokens, so every flash call stays in the first tier.

| Serving metric | plus-brief | flash-brief |
|---|---|---|
| Small-model output (avg) | 103.5 tokens | **85.4 tokens** |
| Small-model total spend | $0.001768 | **$0.000951** |
| `cascade` total spend (threshold 0.85) | $0.006939 | $0.012931 |
| `cascade` escalation | 34% | **56%** |
| `all-frontier` total spend | $0.019848 | $0.018866 |

Small-model spend falls 46.2%, but the higher escalation rate makes the threshold-0.85 cascade bill larger. Neither the 50 small-model nor the 50 frontier responses is empty or truncated by the output budget. Frontier answers are regenerated too, so each run uses its own frontier control; token or verdict differences between runs cannot all be attributed to the small model.

The non-Qwen DeepSeek judge completed all 150 verdicts with `judge_failed=0`. Judged quality and offline economics compare as follows:

| Judged / economics metric | plus-brief | flash-brief |
|---|---|---|
| `all_small` judged success | 44% | **10%** |
| `cascade` judged success (actual threshold 0.85) | 64% | **46%** |
| `all_frontier` judged success | 78% | 80% |
| Effective cost ratio `S/F` | 0.089 | **0.050** |
| Avoidable share | 0.562 | **0.218** |
| Ideal failure-signal savings (offline) | 47.3% | **16.7%** |

In the flash threshold sweep, the highest point short of full escalation is 0.95: 98% escalation, 78% success and $0.019729 total spend — lower success and higher cost than all-frontier. Threshold 1.0 escalates everything and reaches 80% success, but costs **$0.019817**, **5.0% more** than this run's $0.018866 all-frontier control (CPST $0.000270 vs $0.000256). No threshold therefore achieves at least the frontier's success at lower total cost.

The sweep replays routing with the independently sampled `all_small` answers, so its threshold-0.85 row is 52% escalation / 44% success / $0.012203, slightly different from the actual cascade's 56% / 46% / $0.012931; comparisons across thresholds consistently use the replay basis. The conclusion is that **a lower unit price does not offset the quality loss**. Although `S/F` falls to 0.050, the avoidable share drops from 0.562 to 0.218. The 16.7% figure is an offline ideal with perfect knowledge of small-model failure, not a realised router saving. Judge cost is reported separately and estimated at the ledger's frontier rate; it is excluded from these serving-savings comparisons.

### 8.10 What remains

1. ~~Compress small-model output~~: verified in 8.8; the qwen-plus cascade flipped to a narrow win.
2. ~~Shrink the small-model price~~: measured with official Bailian qwen-flash list prices in 8.9. The small-model bill fell, but the quality loss removed every cheaper matched-success operating point.
3. **Rebuild the task mix**: split the 17 missing-input tasks out as should-refuse, add tasks only the small model can handle, and expand the sample to recheck the narrow 7.0% plus-brief win. The avoidable share changes with tasks and model quality; do not reuse the baseline's 30.5%.
4. **Only then change the signal** (semantic entropy, self-consistency, P(True), a RouteLLM-style trained router): recompute the ideal bound for the chosen model (47.3% for plus-brief, 16.7% for flash-brief), then measure how much can be realised.
5. The non-Qwen judge is in place and should be kept.

> Historical reference: 20 even-spaced tasks, threshold 0.66, qwen-max judge (same family) gave 48.03% serving savings and 0% escalation; judged success was frontier 71.4% / cascade 95.0% / small 95.0%. That round had the truncation and fabrication-reward defects from 8.4, so the numbers are a process record, not a conclusion.

## 9. Known limits

- Mock `success` is a probability event, not a quality label; a real evaluation needs task-level rubrics or human annotation.
- Confidence is a rule plus stable jitter (mock) or mean token probability (real); the 50-task run shows mean token probability has no routing power, so the signal must be replaced before production.
- Small-model output length dominates real cost; the real evaluation now fixes `max_tokens=1024`, and any policy comparison must fix the output budget.
- Mock uses illustrative prices; every real ledger binds its model-specific official Bailian rates and FX through `pricing_file`, which must be checked before cross-run comparisons.
- 50 real tasks are still a small sample: complex has only 10 tasks and 34% of tasks lack required input. The negative baseline, narrow plus-brief win and negative flash-brief result all need larger-sample confirmation.
- The judge has its own bias and cost, which can far exceed serving spend (especially for flash all-small); report `CPST (incl. judge)` separately from serving CPST and count judge-side failures separately.
