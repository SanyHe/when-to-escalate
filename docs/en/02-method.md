# 02 · Method and Implementation

> How the ledger is computed, how routing works, how the engine escalates, and how the gateway is exposed. File references are at the end of each section.

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
| `task` | input unit of work | `task_id`, `kind`, `prompt`, `expected_difficulty`, `tags`, `created_at` |
| `route_decision` | routing decision for one attempt | `policy`, `selected_model`, `confidence`, `escalated`, `reason` |
| `model_response` | model output | `model`, `content`, `success`, `latency_ms`, `usage`, optional `confidence` |
| `cost_record` | task-level ledger row | `model`, `attempts`, `cost_usd`, `latency_ms`, `success`, `cost_per_successful_task_usd` |

Enums:

- `kind`: `simple | medium | complex`
- `expected_difficulty`: `low | medium | high`
- `policy`: `all_frontier | cascade | all_small`
- `selected_model` / `model`: `small | frontier`

Cross-field rules (JSON Schema plus explicit checks):

- `usage.total_tokens = prompt_tokens + completion_tokens`
- a failed task must have `cost_per_successful_task_usd = 0`
- a cascade escalation must select `frontier`; fixed policies never escalate

Implementation: [`cascade/src/schema.py`](../../cascade/src/schema.py). Export schemas with `python3 cascade/src/schema.py --export`.

## 3. Synthetic task flow

`gen_tasks.py` generates 100 tasks from fixed templates and a fixed seed:

- 50 `simple` (weather, email triage, calendar confirmation);
- 30 `medium`;
- 20 `complex` (cross-platform price comparison, long-horizon research).

> The initial spec suggested an approximately 80/20 simple/complex split; the implementation uses **50/30/20** so mid-difficulty threshold behaviour is observable. This deviation is recorded at implementation time. The panel exposes traffic-mix weights so the conclusion can be extrapolated.

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
