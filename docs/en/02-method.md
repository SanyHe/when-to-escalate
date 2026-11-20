# 02 · Method and Implementation

> The routing infrastructure for an always-on agent, in two layers. The **personal policy layer** decides which model tier a decision point is even allowed to use (buckets + hard constraints); the **cascade engine** (§1–§9) decides small → frontier within an allowed, routable bucket. How the ledger is computed, how routing works, how the engine escalates, and how the gateway is exposed. File references are at the end of each section.

## 0 · Always-on agent: two layers

This project splits the routing job into two layers that are deliberately
independent:

1. **Personal policy layer** — resolves one bucket per decision point, *before
   any model call*. Pure function, deterministic, no network.
   [`cascade/src/personal_policy.py`](../../cascade/src/personal_policy.py) +
   [`cascade/configs/personal_policy.yaml`](../../cascade/configs/personal_policy.yaml).
2. **Cascade engine layer** — within a bucket allowed to escalate, decides
   small → frontier. §1–§9 below describe this layer.

### Decision buckets (B0–B5)

`assign_bucket(decision, config)` resolves one bucket with this resolution order
(first match wins): **hard constraints → consequence → latency → classifier
uncertainty** (consequence confidence below `consequence_confidence_floor` =
0.80 steps the bucket up one level: read → suggest → reversible → irreversible).

| Bucket | Model | Confirmation | Verifier | Escalate | SLO |
|---|---|---|---|---|---|
| `B0_sense` | `none` | none | rule | no | 200 ms |
| `B1_read` | `small` | none | none | no | 2 s |
| `B2_draft` | `small` | inline | schema | on failure | 3 s |
| `B3_act_reversible` | `small` | after_the_fact | tool_result | on failure | 5 s |
| `B4_act_irreversible` | `frontier` | required | human | no | 10 s |
| `B5_background` | `small` | none | sample | no | 60 s (batch) |

Only `B2_draft` and `B3_act_reversible` may escalate to the frontier
(`routing.enabled_buckets`); every other bucket keeps a fixed model so cost and
risk stay predictable.

### Hard constraints

`hard_constraints` run before any cost optimisation and can override the bucket:

- `local_only` — data never leaves the device: force the `local` model, never
  escalate; queue if the local model is unavailable.
- `user_absent_irreversible` — an irreversible write while `user_present` is
  false is queued for confirmation.
- `degraded_device` — `low_battery` / `weak_network` defer paid work to
  `B5_background`; `B0_sense` is preserved.
- `budget_exhausted` — only `B0_sense` / `B1_read` / `B2_draft` may run; the
  rest are deferred.

### Promotion gates

A bucket is promoted to quality routing only when `check_promotion(stats,
config)` reports *every* gate green:

| Gate | Threshold |
|---|---|
| decisions | ≥ 300 |
| verifier coverage | ≥ 0.90 |
| small-model accept rate | ≥ 0.80 |
| cost reduction | ≥ 0.10 |
| error-rate ratio | ≤ 1.20 |

### Telemetry: the agent's verifier is user behaviour

An always-on agent has no separate test harness — the verifier is what the user
does next. [`cascade/src/telemetry.py`](../../cascade/src/telemetry.py) records
one JSONL line per decision point with a fixed 27-field contract
(`FIELD_ORDER`); `build_event()` validates and emits every field, and unknown
fields are rejected so the schema stays stable.

Required fields: `decision_id`, `ts`, `bucket`, `model`, `outcome`. Outcomes:
`pending`, `user_accepted`, `user_edited`, `user_undone`, `ignored`, `failed`.
Without `user_edited` and `user_undone`, the agent has no verifier at all.

`summarize_events()` aggregates per bucket: decision count, escalation count,
accept rate, undo rate, error rate, average cost and average latency. These are
the numbers that feed the promotion gates.

### Current status of this layer

The policy layer and telemetry are **offline and simulated today**.
[`cascade/src/replay_decisions.py`](../../cascade/src/replay_decisions.py)
proves the buckets, hard constraints and telemetry add up to usable
bucket-level numbers from fixed priors (see
[`data/telemetry/replay_summary.md`](../../data/telemetry/replay_summary.md) —
outcomes, tokens and latencies are synthetic; prices are illustrative). The
layer is **not yet wired into the live gateway**: `gateway.py` / `engine.py`
serve the cascade engine directly, so the buckets above describe the policy the
agent *should* apply, not a path that is already live.

## 1. End-to-end path

```
task.json ──> router(confidence) ──> CascadeEngine
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
              small backend                      frontier backend
                    │                                   │
                    └──────────────> cost_record <───────┘
                                      │
                              metrics / ledger / gateway
```

The key constraint: **routing and cost are pure functions**. Model calls come through a `complete(task, attempt)` interface, so the ledger can be fully verified with mock backends before real HTTP backends are plugged in.

## 2. Data contracts

Four objects, all strict JSON (UTF-8, fixed keys, no extra fields):

| Object | Purpose | Key fields |
|---|---|---|
| `task` | input unit of work | `task_id`, `kind`, `prompt`, `expected_difficulty`, `tags`, `created_at`, optional `task_class` / `verification` |
| `route_decision` | routing decision for one attempt | `policy`, `selected_model`, `confidence`, `escalated`, `reason` |
| `model_response` | model output | `model`, `content`, `success`, `latency_ms`, `usage`, optional `confidence` |
| `cost_record` | task-level ledger row | `model`, `attempts`, `cost_usd`, `latency_ms`, `success`, `cost_per_successful_task_usd` |

Enums:

- `kind`: `simple | medium | complex`
- `expected_difficulty`: `low | medium | high`
- `task_class`: `should_refuse | small_sufficient | frontier_required`
- `verification.type`: `exact_match | field_match | regex | json_schema | refusal | llm_judge`
- `policy`: `all_frontier | cascade | all_small`
- `selected_model` / `model`: `small | frontier`

Cross-field rules (JSON Schema plus explicit checks):

- `usage.total_tokens = prompt_tokens + completion_tokens`
- a failed task must have `cost_per_successful_task_usd = 0`
- a cascade escalation must select `frontier`; fixed policies never escalate

Implementation: [`cascade/src/schema.py`](../../cascade/src/schema.py). Export schemas with `python3 cascade/src/schema.py --export`.

## 3. Synthetic task flow

`gen_tasks.py` generates 100 tasks from fixed templates and a fixed seed. It allocates by `task_class` first, then by difficulty inside each class:

- **`should_refuse`, 20 tasks**: live data, attachments or access are missing; the correct behaviour is to say what is missing instead of inventing it;
- **`small_sufficient`, 50 tasks**: each has a deterministic verifier (exact value, fields, regex or JSON);
- **`frontier_required`, 30 tasks**: open-ended analysis and design, graded by a rubric or an LLM judge.

Difficulty stays at **50/30/20** (simple/medium/complex) so the mock ledger remains comparable with earlier runs. Every task carries a `verification` spec; offline grading uses the deterministic verifier first and only calls the judge for `llm_judge` tasks.

> This rebuild replaces task content but keeps the `task_id` numbering scheme. Real ledgers produced before 2026-11-11 used the previous task file; re-judging them requires their original source and must not reuse the new `seed_tasks.jsonl`.

Two runs produce byte-identical output; all 100 `task_id`s and prompts are unique. Output: `data/synthetic/seed_tasks.jsonl`.

Implementation: [`cascade/src/gen_tasks.py`](../../cascade/src/gen_tasks.py).

## 4. Pricing, retry premium and CPST

Pricing is pure data (`cascade/configs/pricing.yaml`), in USD per million tokens:

| Model | Input | Output |
|---|---|---|
| `small` | 0.15 | 0.60 |
| `frontier` | 3.00 | 12.00 |

> These are **example prices** chosen for easy hand calculation. They are not a vendor quote.

Formulas:

- single-call cost = `prompt_tokens / 1e6 * input + completion_tokens / 1e6 * output`
- expected attempts = `1 / p` for per-attempt success probability `p`
- retry premium = `1 / p - 1`; `p = 0.70` → 1.4286 attempts → +42.86%
- **CPST** = total cost of successful tasks ÷ number of successful tasks

CPST counts only tasks that eventually succeed; wasted spend on failures is reported separately as `failed_cost_usd`, so the evaluation answers both "what does success cost" and "how much did failure waste".

Implementation: [`cascade/src/pricing.py`](../../cascade/src/pricing.py).

## 5. Router

The router starts from a **deterministic prior**: confidence comes from task difficulty plus a stable jitter (±0.03) derived from `task_id`, so tasks at the same difficulty still differ.

With real backends, the adapter requests token `logprobs` and reports `exp(mean(logprob))` — the geometric mean token probability — as **model-reported confidence**. The engine replaces the prior with it before the escalation check. When no log-probabilities are available (mock replay, unsupported provider, or `CASCADE_LOGPROBS=0`), the rule prior is used.

| Difficulty | Base confidence |
|---|---|
| `low` | 0.93 |
| `medium` | 0.78 |
| `high` | 0.52 |

Default threshold: `confidence_threshold = 0.66` (`cascade/configs/policy.yaml`).

Rules:

- `all_frontier` → select `frontier`, `confidence = 1.0`, never escalate;
- `all_small` → select `small`, never escalate; retry the small model up to `max_attempts = 2`;
- `cascade` → select `small` first; escalate to `frontier` when either:
  1. the small call failed (fallback), or
  2. confidence `< threshold` (quality check).

`max_attempts`:

| Policy | Max attempts |
|---|---|
| `all_frontier` | 1 |
| `all_small` | 2 |
| `cascade` | 1 small + at most 1 frontier |

Implementation: [`cascade/src/router.py`](../../cascade/src/router.py).

> Confidence priority: model-reported logprob confidence, then the rule prior. `confidence_by_difficulty` is only a fallback. To reduce false escalations further, add self-consistency or a multi-token margin calibration on top.

## 6. Cascade engine

`CascadeEngine` is backend-agnostic: it receives `{small, frontier}` objects implementing `complete(task, attempt)`. Each task produces:

```json
{
  "task_id": "task_0001",
  "policy": "cascade",
  "route_decisions": [ ... ],
  "responses": [ ... ],
  "cost_record": { ... }
}
```

Policy order:

- **all_frontier**: call frontier; retry up to `max_attempts` on failure.
- **all_small**: call small; retry once on failure (2 attempts by default).
- **cascade**:
  1. call small (attempt = 1);
  2. if it failed → escalate to frontier, reason `fallback`;
  3. else if confidence is below the threshold → escalate to frontier, reason `quality check`;
  4. success = small succeeded **or** frontier succeeded; cost = sum of all attempts.

Notes:

- Escalation is not "retry the small model"; it switches model. `max_attempts` for cascade therefore means "small attempt + frontier attempt", not same-model retries.
- Every attempt is appended to `responses` and `route_decisions`; cost and latency are summed before producing `cost_record`.
- When the small response carries `confidence`, the first decision's `confidence` and `reason` are updated to the model-reported value.
- `export_trace()` renders a readable decision chain for debugging and evidence.

Implementation: [`cascade/src/engine.py`](../../cascade/src/engine.py).

## 7. OpenAI-compatible gateway

The gateway turns a standard OpenAI request into a task and delegates to the engine:

- `POST /v1/chat/completions`
  - uses the last `role = user` message as the prompt;
  - classifies by prompt length: ≤120 chars → `simple/low`, ≤320 → `medium/medium`, otherwise `complex/high`;
  - builds `task_id = req_<sha256(prompt + created_at)[:12]>`;
  - returns standard `id/object/created/model/choices/usage` plus a `cascade` block (policy, confidence, escalation, attempts, cost, decisions).
- `GET /healthz`: returns `status/policy/backends`, or a clear `503` when endpoints are missing.
- `GET /v1/models`: minimal model list for client probes.

Safety and reliability:

- endpoints and keys are environment-only: `CASCADE_SMALL_BASE_URL`, `CASCADE_SMALL_MODEL`, `CASCADE_FRONTIER_BASE_URL`, `CASCADE_FRONTIER_MODEL`, `CASCADE_FRONTIER_API_KEY`;
- transport failures (timeout, HTTP 5xx, network error) become `success: false` responses, so the engine escalates instead of raising;
- gateway errors never echo stack traces, URLs or keys;
- streaming is unsupported; `stream: true` returns an OpenAI-style `400`.

Implementation: [`cascade/src/gateway.py`](../../cascade/src/gateway.py), [`cascade/src/backends.py`](../../cascade/src/backends.py).

## 8. Determinism and configuration

- Task generation, confidence jitter and mock responses are keyed by stable hashes.
- Pricing and policy are YAML data; changing a threshold or price does not require code changes.
- `replay.py` runs all three policies and writes:
  - `data/eval/mock_ledger.json` (traces + metrics);
  - `data/eval/mock_ledger.md` (comparison table);
  - `web/data/ledger.json` (tasks and raw attempt responses for the panel).
- The panel recomputes in the browser with `web/js/metrics.js`; `node cascade/tests/verify_web_metrics.js` compares it against the Python metrics.

## 9. Mock boundary

`MockBackend` simulates success/failure, token usage and latency from fixed probabilities and deterministic jitter:

- small-model success falls with difficulty; frontier succeeds more often;
- failed calls still consume prompt tokens (completion is zero);
- latency and token counts come from stable hashes.

These numbers exist to validate the ledger and the product surface. Real model behaviour, prices and latency must come from F2.5. Until then, every mock metric must be labelled MOCK in the UI and in the docs.
