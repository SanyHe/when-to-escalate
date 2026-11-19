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
# Verifier-first gate: accept on deterministic-check pass, escalate on fail,
# fall back to confidence when no verifier exists; live results are in 8.14.
python3 cascade/src/real_eval.py --limit 50 --max-tokens 1024 --threshold 0.85 \
    --small-model qwen-plus --frontier-model qwen-max \
    --small-system-prompt "Be brief: answer in at most 120 words. Do not restate the question or add preamble." \
    --pricing cascade/configs/pricing.qwen.yaml --escalation-mode verifier_first \
    --sleep 3 --timeout 120 \
    --out data/eval/real_ledger_plus_v3.json --md-out data/eval/real_ledger_plus_v3.md
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

The external non-Qwen judge completed all 150 verdicts with `judge_failed=0`. Judged quality and offline economics compare as follows:

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
3. **Rebuild the task mix**: the infrastructure is in place (8.11); the real expanded run still waits for budget confirmation. The avoidable share changes with tasks and model quality; do not reuse the baseline's 30.5%.
4. **Only then change the signal** (semantic entropy, self-consistency, P(True), a RouteLLM-style trained router): recompute the ideal bound for the chosen model (47.3% for plus-brief, 16.7% for flash-brief), then measure how much can be realised.
5. The non-Qwen judge is in place and should be kept.

### 8.11 Task-mix rebuild and deterministic verifiers (zero API)

Groundwork for item 3, with no model calls:

- **Contract extension**: `task` gains optional `task_class` (`should_refuse | small_sufficient | frontier_required`) and `verification`. Older task files stay valid and fall back to the previous behaviour.
- **New task flow**: 100 tasks = 20 should-refuse / 50 small-sufficient / 30 frontier-required, while difficulty stays 50/30/20 (simple/medium/complex) so the mock ledger remains comparable.
- **Deterministic verifier**: `cascade/src/verifier.py` supports `exact_match`, `field_match`, `regex`, `json_schema` and `refusal`, returning `passed / failed / needs_judge`. Numeric matches use digit boundaries (`3072` does not match `13072`); text matches normalise width, case and whitespace.
- **Refusal grading**: `refusal` requires an explicit statement of which input is missing and rejects the fabrication patterns attached to the template (concrete temperatures, dates, percentages). This is a reproducible operational rule, not a full semantic judgement.
- **Grading integration**: `judge_ledger.py` now tries the verifier first and only falls back to the LLM judge on `needs_judge`; records carry `judged_by` and `verification_type`, and judge cost only covers real LLM fallbacks.
- **Regrade mode**: `judge_ledger.py --regrade-verifiers` reuses stored LLM verdicts and re-runs only the deterministic verifiers, with no API calls, so verifier-rule changes can be reapplied reproducibly.
- **Stratified sampling**: `real_eval.py` stratifies by `task_class` first, preserving the 20/50/30 ratio; older tasks without `task_class` still stratify by `kind`.

Verification (zero API): `178 passed`; `node cascade/tests/verify_web_metrics.js` passes; the rebuilt mock ledger shows the cascade saving 47.84% at 99% success versus 97% for all-frontier (still MOCK numbers).

Boundary: no real API was called and no new real ledger was produced. The old real ledgers were generated against the previous task content, which this rebuild replaced; they must not be re-judged against the new `seed_tasks.jsonl`. See 8.12 for the new-mix real check.

> Historical reference: 20 even-spaced tasks, threshold 0.66, qwen-max judge (same family) gave 48.03% serving savings and 0% escalation; judged success was frontier 71.4% / cascade 95.0% / small 95.0%. That round had the truncation and fabrication-reward defects from 8.4, so the numbers are a process record, not a conclusion.

### 8.12 New-mix real check: no matched-success saving after fixing refusal false negatives

Using the 20/50/30 flow from 8.11, we sampled 50 tasks by `task_class` (10 refusal / 25 small-sufficient / 15 frontier-required) with `max_tokens=1024`, threshold 0.85 and official prices. Serving ran all three policies; grading used deterministic verifiers on 35 tasks and an external non-Qwen judge on 15 (45 fallbacks per run = 15 tasks × 3 policies, 70% fewer than full judging). Artifacts: `data/eval/real_ledger_{plus,flash}_v2*`.

| Policy | Judged success | Serving CPST | Serving cost | Escalation | CPST incl. judge |
|---|---|---|---|---|---|
| plus all-frontier | 90% | $0.000279 | $0.015219 | 0% | $0.000662 |
| plus cascade | 80% | $0.000098 | $0.005153 | 12% | $0.000675 |
| plus all-small | 82% | $0.000024 | $0.001461 | 0% | $0.000401 |
| flash all-frontier | 96% | $0.000293 | $0.015796 | 0% | $0.000785 |
| flash cascade | 84% | $0.000135 | $0.008107 | 28% | $0.000515 |
| flash all-small | 76% | $0.000012 | $0.000665 | 0% | $0.000592 |

Passed / total by task class:

| Task class (n) | plus frontier | plus cascade | plus small | flash frontier | flash cascade | flash small |
|---|---|---|---|---|---|---|
| Should refuse (10) | 7 | 6 | 5 | 10 | 6 | 1 |
| Small sufficient (25) | 25 | 25 | 25 | 25 | 24 | 24 |
| Frontier required (15) | 13 | 9 | 11 | 13 | 12 | 13 |

**A grading defect was fixed first.** The initial refusal phrase list only covered fixed phrasings such as "not provided" and "missing", and marked valid refusals like "the content was not directly provided", "no concrete details" or "I need to see ... could you provide it" as failures. After the fix, frontier success on the same answers rose from 82% to 90% (plus) and 86% to 96% (flash), and the refusal class rose from 4-5/10 to 7-10/10. `--regrade-verifiers` reproduces this re-grade without new API calls. Keyword-based refusal verification is highly phrasing-sensitive; template-level paraphrase coverage and human spot checks are mandatory.

**No matched-success saving was measured.** plus: frontier 90% / $0.000279, cascade 80% / $0.000098, small 82% / $0.000024. Cascade serving CPST is 65% lower, but per-request success is 10 pp lower, and cascade is both below all-small and about 3.5x its total cost, so confidence-based escalation added no value for plus in this run. flash: frontier 96% / $0.000293, cascade 84% / $0.000135, small 76% / $0.000012; cascade is 8 pp above all-small and 54% cheaper per success than frontier, but still 12 pp below frontier. Escalation helps flash, but not enough to close the gap.

**The threshold sweep is an upper-bound hypothesis.** Replaying all-small records plus all-frontier records gives 90% at 0.85 for plus (CPST $0.000127) and 92% at 0.85 for flash ($0.000212); the actual cascades reached only 80% and 84%. For plus, the cascade's own small answers differ from all-small on 7/50 tasks, and one of six escalated tasks fell back to the small answer after frontier failed; the replay models neither effect. The 0.85-0.90 "matched" points are therefore not realised results. Judge cost is offline evaluation overhead: $0.0172-0.0231 per plus policy and $0.0160-0.0236 per flash policy, above serving cost; with judge cost included, plus cascade is already slightly more expensive than frontier. It must not be added to online CPST.

**Conclusion and next step**: the verifier fix raised the frontier ceiling from 82% to 90%/96%, so the old-mix result (plus 7.0% cheaper, flash 5.0% more expensive at matched success) no longer holds. What remains is a trade-off: 10-12 pp lower success for 54-65% lower serving CPST. F2.5 stays in progress. Next: repeat each policy three times or extend to at least 150 tasks and report mean and range; make the threshold replay use the cascade's own small answers and model fallback; routing-signal comparison is in 8.13.

### 8.13 Routing signals: a verifier gate beats mean token probability (offline replay)

We replayed the two recorded ledgers from 8.12 through five signal families (`cascade/src/router_signals.py`, **zero model calls**). Each signal is reduced to its cheapest point at "success >= all-frontier"; the table below uses the fixed 0.85 threshold so nothing is tuned on the same data.

| Signal | plus success / total / CPST / escalation | flash success / total / CPST / escalation |
|---|---|---|
| all-frontier (baseline) | 90% / $0.015219 / $0.000279 / 0% | 96% / $0.015796 / $0.000293 / 0% |
| mean token probability (today) | 90% / $0.006031 / $0.000127 / 14% | 92% / $0.011560 / $0.000212 / 36% |
| **verifier gate** | **94% / $0.006760 / $0.000124 / 18%** | **96% / $0.011665 / $0.000206 / 40%** |
| **refusal gate (no gold)** | **94% / $0.006760 / $0.000124 / 18%** | **96% / $0.011665 / $0.000206 / 40%** |
| answer length / prompt length | never reaches 90% | reaches 96% only by escalating 100% |
| task-class oracle (metadata) | 86% / $0.012234 / $0.000240 / 0% | 76% / $0.012210 / $0.000272 / 0% |
| keyword router (AUC 0.935) | 90%, but needs 92% of tasks on frontier, cost ~ frontier | 96%, also needs 92% on frontier |
| oracle (perfect router) | 96% / $0.005776 | 98% / $0.004622 |

Rule: run the small model on verifiable tasks, accept a verifier pass and escalate a fail; fall back to the 0.85 confidence gate when no verifier exists. By task class (verifier gate, 0.85):

| Task class (n) | plus passed / cost | flash passed / cost |
|---|---|---|
| Should refuse (10) | 8/10 / $0.002578 | 10/10 / $0.003262 |
| Small sufficient (25) | 25/25 / $0.000199 | 25/25 / $0.000072 |
| Frontier required (15) | 14/15 / $0.003983 | 13/15 / $0.008331 |

Four findings:

1. **The verifier gate reaches or beats frontier success on both models**: plus 94% (frontier 90%), flash 96% (frontier 96%), with total cost 55.6% / 26.2% lower and CPST falling by the same ratio. The gain comes from the refusal class: when the small model fails to flag missing input, the refusal verifier turns that failure into one escalation. Frontier itself fails some refusal tasks (plus 7/10), so the gate can even exceed all-frontier.
2. **The gain does not depend on gold answers.** `exact_match/field_match` compare against the task's stored expected value, so they represent "every task ships a cheap checker". Restricting the gate to the refusal check (which needs no gold) and falling back to confidence for everything else produces **identical** numbers at the pre-registered 0.85 threshold: plus small-sufficient tasks were already 25/25, and flash's only small-sufficient failure (a reversed word) had confidence 0.84 and would be escalated anyway. The gold verifier only adds value at the tuned 0.5 point, and that advantage rests on one task.
3. **Knowing the task class is not routing.** Sending every `frontier_required` task straight to frontier yields only 86%/76% success, because refusal tasks left on the small model still fail. A keyword router with AUC 0.935 must still send 92% of tasks to frontier to reach matched success, at which point cost collapses to all-frontier. **AUC is not savings; the question is how many frontier calls a point needs at matched success.**
4. **Free signals (answer length, prompt length) have no filtering power**: plus never reaches 90% at any threshold, and flash only reaches 96% by escalating everything.

**Scope**: every number here is an offline replay over all-small answers, not a live cascade. Section 8.12 showed replay can differ from the live cascade by 8-10 pp (7/50 different small answers, and frontier-failure fallback is not modelled). This section therefore selects a signal; it does not report realised savings. See 8.14 for the live verifier-first run.

### 8.14 Verifier-first live run: better than the confidence gate, still below frontier (2026-11-18)

We implemented `--escalation-mode verifier_first` (`engine.py::_verifier_decision`): run the small model first, accept a deterministic-verifier pass, escalate a verifier failure, and fall back to the 0.85 confidence gate when the task has no verifier. Small-model HTTP failure still escalates via fallback. The run used exactly the v2 conditions (50 stratified tasks, qwen-plus brief ≤120 words → qwen-max, `max_tokens=1024`, threshold 0.85, `pricing.qwen.yaml`, the same external non-Qwen judge). Artifacts: `data/eval/real_ledger_plus_v3{,_judged}.{json,md}`; zero judge failures (105 verifier + 45 LLM verdicts).

| Policy | Judged success | Total cost | CPST (serving) | CPST (incl. judge) | Escalation |
|---|---|---|---|---|---|
| `all_frontier` | 48/50 = **96%** | $0.015675 | $0.000292 | $0.000991 | 0% |
| `cascade` (verifier gate) | 43/50 = **86%** | $0.005587 | $0.000087 | $0.000695 | 16% |
| `all_small` | 40/50 = **80%** | $0.001470 | $0.000023 | $0.000509 | 0% |

Cascade passes by class: should-refuse 9/10, small-sufficient 25/25, frontier-required 9/15. Frontier failed only two tasks this round (0039, 0081, both frontier-required).

**Comparison with the confidence gate (v2), with a cross-run noise warning**: v2 was frontier 90% / cascade 80% / all-small 82% in its own round; this round is 96% / 86% / 80%. Only 24/50 all-frontier answers are identical across the two rounds (sampling drift), so "80% → 86%" cannot be credited to the gate alone. The more meaningful same-round contrast is the **inversion of cascade versus all-small**: in v2 cascade (80%) sat below all-small (82%), i.e. routing destroyed value; in v3 cascade (86%) sits above all-small (80%), i.e. routing now adds value.

**Three measured findings**:

1. **Escalation decisions on verifiable tasks reproduced the replay exactly.** The five should-refuse tasks (0013/0016/0030/0041/0065) escalated on refusal-verifier failure, matching 8.13 task for task; all 25 small-sufficient tasks passed the verifier with zero escalations. Should-refuse rose from 6/10 (v2) to 9/10. This is the gate's most stable gain.
2. **The remaining gap is entirely in unverifiable tasks, and it shows up as high-confidence errors.** Of the 42 non-escalated tasks, five failed — all frontier-required, with confidences 0.92 / 0.88 / 0.88 / 0.88 / 0.87, every one above the 0.85 threshold yet genuinely wrong (a mis-computed valuation sensitivity, a misunderstood `cache.setdefault` semantic, invented figures the prompt never supplied). Mean token probability is **systematically blind** to these failures, which is why the replay's "frontier_required 14/15" did not reproduce live.
3. **"Escalated = frontier quality" does not hold.** Two of the eight escalated tasks still failed: after escalation, 0041's frontier answer again invented input, and 0006's frontier answer was judged "a generic framework with no executable steps". The cascade's frontier call and all-frontier's call are independent samples, so escalation does not guarantee this round's 96%.

**Cost accounting**: cascade total cost is 35.6% of frontier (64.4% saved) and serving CPST is 70% lower, but success is 10 pp lower — **still not a matched-success saving**. Including judge cost, cascade $0.000695 remains below frontier $0.000991 (30% lower). The judge bill ($0.026) is over 4x the cascade's own serving cost ($0.0056), which again argues for wider deterministic-verifier coverage.

**Next**: F2.5 stays in progress. Two options — (a) test a strict variant that escalates every unverifiable task (estimated ~$0.009, 60% of frontier) to see whether success passes 92%; (b) repeat this configuration three times to quantify cross-run noise before judging whether the gate's gain is significant.

### 8.15 Strict variant: escalating every unverifiable task still loses to all-frontier (2026-11-19)

We added `--escalation-mode verifier_strict`: verifiable tasks behave as in verifier-first, while every unverifiable task escalates regardless of confidence. Same 50 tasks and conditions (qwen-plus brief ≤120 words → qwen-max, `max_tokens=1024`, `pricing.qwen.yaml`, the same external non-Qwen judge). Artifacts: `data/eval/real_ledger_plus_v4_strict{,_judged}.{json,md}`; zero judge failures (105 verifier + 45 LLM verdicts).

Routing matched the design exactly: 30 verifier passes accepted, 5 refusal-verifier failures escalated, 15 unverifiable tasks escalated by strict mode, 0 HTTP fallbacks; escalation 40%. Serving cost $0.015270 = $0.000315 small-only + $0.014955 escalated.

| Policy | Judged success | Total cost | CPST (serving) | CPST (incl. judge) | Escalation |
|---|---|---|---|---|---|
| `all_frontier` | 44/50 = **88%** | $0.015762 | $0.000258 | $0.000728 | 0% |
| `cascade` (strict) | 43/50 = **86%** | $0.015270 | $0.000259 | $0.000769 | 40% |
| `all_small` | 39/50 = **78%** | $0.001466 | $0.000022 | $0.000404 | 0% |

Passes by class: strict refusal 6/10, small-sufficient 25/25, frontier-required 12/15; all-frontier 8/10, 25/25, 11/15; all-small 5/10, 25/25, 9/15.

**Four findings**:

1. **Strict turns the "high-confidence error" problem into a frontier-quality problem without solving it.** All 15 unverifiable tasks went to the frontier and three still failed (0006, 0039, 0087); four of the five escalated refusal tasks still had frontier answers that invented input, leaving refusal at 6/10. Strict's 86% ties v3's verifier-first 86% and remains 2 pp below the same-round frontier.
2. **All-frontier dominates on cost.** Serving cost is only 3.1% lower ($0.015270 vs $0.015762), serving CPST is slightly higher ($0.000259 vs $0.000258), and all-in CPST is 5.6% higher ($0.000769 vs $0.000728); judge cost is also higher ($0.021934 vs $0.020717). There is neither matched success nor a cost advantage at matched success.
3. **The gain over all-small is just paying the frontier for unverifiable tasks.** Strict is 8 pp above all-small but costs 10.4x as much; its 12/15 unverifiable passes versus frontier's 11/15 are two independent samples, not a routing gain. On unverifiable tasks strict is equivalent to calling the frontier directly.
4. **The frontier ceiling itself drifts.** On the same 50 tasks, frontier scored 96% in v3 and 88% in v4 (refusal 8/10, frontier-required 11/15), so the earlier 96% was not a stable ceiling. Any single-run claim of "beating frontier" needs repeated runs.

**Next**: strict does not meet F2.5's matched-success saving test, so F2.5 stays in progress. Options: (a) repeat this configuration three times to establish means and ranges; (b) widen deterministic-verifier coverage (arithmetic recomputation, code execution, numeric grounding) to reduce dependence on the LLM judge and unverifiable tasks; (c) if productised, describe it honestly as a cheaper-but-less-accurate option, never as matched-success savings.

## 9. Known limits

- Mock `success` is a probability event, not a quality label; a real evaluation needs task-level rubrics or human annotation.
- Confidence is a rule plus stable jitter (mock) or mean token probability (real); the 50-task run shows mean token probability has no routing power, so the signal must be replaced before production.
- The verifier gate and keyword router in 8.13 are offline replays over all-small answers. Sections 8.14/8.15 run the verifier gate and strict variant live, but both single runs remain below the same-round frontier (86% vs 88%), and replay can differ from a live cascade by 8-10 pp. A high AUC is not savings: the keyword router scores AUC 0.935 yet still needs 92% frontier calls at matched success.
- Strict raises escalation to 40% and brings serving cost close to all-frontier, yet success stays 2 pp lower and all-in CPST is 5.6% higher; on this single sample all-frontier dominates strict.
- The frontier ceiling drifts across runs: 96% in v3 versus 88% in v4 on the same tasks, so a single run that beats frontier is not evidence for F2.5.
- Refusal verification only checks "states the input is missing and does not fabricate"; it is not full semantic refusal grading. `exact_match/field_match` rely on stored expected answers, so production needs an equivalent tool check or recomputation.
- Small-model output length dominates real cost; the real evaluation now fixes `max_tokens=1024`, and any policy comparison must fix the output budget.
- Mock uses illustrative prices; every real ledger binds its model-specific official Bailian rates and FX through `pricing_file`, which must be checked before cross-run comparisons.
- The new 50-task sample is still a single small run (10 refusal / 25 small-sufficient / 15 frontier-required); one task moves success by 2 pp, and the same frontier model passed 7/10 versus 10/10 refusal tasks in two runs. Repeat before drawing conclusions.
- Keyword refusal verification is phrasing-sensitive: adding paraphrases raised frontier success by 8-10 pp, so the grading rule itself changes the measured ceiling. Keep template-level positive and negative cases plus human spot checks.
- The threshold sweep replays all-small answers and does not model cascade answer drift or frontier-failure fallback; it is a tool for choosing a threshold, not evidence of a realised matched-success point.
- The judge has its own bias and cost, which can far exceed serving spend (especially for flash all-small); report `CPST (incl. judge)` separately from serving CPST and count judge-side failures separately.
