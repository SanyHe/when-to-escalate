# AGENTS.md — When to Escalate

> This is the harness entry file. Read it first at the start of every session.
> It defines how the agent works on this repo. Following these rules is what
> makes the work reliable across sessions.

## 1. Startup Workflow (do this before writing any code)

1. Read `private/trae-progress.md` — find the **Current Verified State** and the **Next best action**.
2. Read `private/feature_list.json` — identify the feature currently `in_progress` or the highest-priority `not_started` feature. Only **one** feature may be `in_progress` at a time.
3. Read the sections relevant to that feature in `private/PLAN.md` (scope) and [`docs/02-method.md`](./docs/02-method.md) (contracts, routing, ledger) / [`docs/03-eval.md`](./docs/03-eval.md) (metrics, milestones).
4. Confirm the environment with `./init.sh` (installs dev deps, runs verification). If verification fails, fix the baseline before doing anything else.

> Harness state and the internal spec live in `private/`, which is gitignored
> and never published. A fresh clone contains only the public files above.

## 2. Working Rules

- **One feature at a time.** Never start a new feature while another is `in_progress`.
- **Evidence before marking `passing`.** A feature is `passing` only when:
  - Its `verification` steps have been run and recorded in `evidence`.
  - The output is reproducible (fixed seeds, deterministic scripts).
  - No other feature regressed (full `pytest cascade/tests/` still green).
- **Stop agents from declaring victory too early.** If you cannot run the verification (e.g. no GPU / no API endpoint for the real-backend eval), mark the feature `blocked` with a documented reason — do not mark it `passing`.
- **Strict milestone order.** M1 must pass before M2; M2 before M3. Do not skip ahead.
- **Scope discipline.** Implement only the selected feature. Do not pre-build M3 infrastructure while in M1.
- **Mock values are labelled mock.** Whenever a metric comes from the deterministic mock backend rather than a real model, say so in the report, the UI, and the evidence.
- **Code comments in English.** All source comments must be in English.
- **No secrets in the repo.** Endpoints/keys use environment variables only. Synthetic data only; real data stays in `private/` (gitignored).

## 3. Definition of Done for a Feature

A feature is done when all of the following are true:

1. The harness state under `private/` marks the feature `passing` (or `blocked`) and records concrete, reproducible evidence (test output, file paths, metrics).
2. The session log under `private/` records goal, changes, verification run, evidence, known risks and next action.
3. `python3 -m pytest cascade/tests/ -v` passes (for any feature touching cascade/data code).
4. No half-finished work is left uncommitted or unrecorded.

## 4. Project Commands & Paths

| Purpose | Command |
|---|---|
| Install dev deps | `pip install jsonschema pyyaml pytest fastapi httpx uvicorn` |
| Verify (tests) | `python3 -m pytest cascade/tests/ -v` |
| Verify web metrics | `node cascade/tests/verify_web_metrics.js` |
| Regenerate seed tasks | `python3 cascade/src/gen_tasks.py` |
| Build the three-policy mock ledger | `python3 cascade/src/replay.py` |
| Run the real three-policy eval | `python3 cascade/src/real_eval.py --limit 5 --pricing cascade/configs/pricing.qwen.yaml` |
| Judge a real ledger offline | `python3 cascade/src/judge_ledger.py --ledger data/eval/real_ledger.json` |
| Serve the gateway (needs backends) | `uvicorn cascade.src.gateway:app --port 8000` |
| Preview the static panel | `python3 -m http.server 8765 --directory web` |

Key paths:
- Schemas & validation: [`cascade/src/schema.py`](./cascade/src/schema.py)
- Pricing & cost functions: [`cascade/src/pricing.py`](./cascade/src/pricing.py)
- Rule router: [`cascade/src/router.py`](./cascade/src/router.py)
- Cascade engine: [`cascade/src/engine.py`](./cascade/src/engine.py)
- Backend adapters: [`cascade/src/backends.py`](./cascade/src/backends.py)
- OpenAI-compatible gateway: [`cascade/src/gateway.py`](./cascade/src/gateway.py)
- Replay / ledger: [`cascade/src/replay.py`](./cascade/src/replay.py)
- Real-backend eval: [`cascade/src/real_eval.py`](./cascade/src/real_eval.py)
- Offline judge: [`cascade/src/judge.py`](./cascade/src/judge.py) / [`cascade/src/judge_ledger.py`](./cascade/src/judge_ledger.py)
- Pricing config: [`cascade/configs/pricing.yaml`](./cascade/configs/pricing.yaml)
- Policy config: [`cascade/configs/policy.yaml`](./cascade/configs/policy.yaml)
- Synthetic data: [`data/synthetic/`](./data/synthetic/)
- Static panel: [`web/`](./web/)

## 5. Backends & Compute

Tests run offline against deterministic mocks, so no GPU is required. Real
backends (local vLLM or an OpenAI-compatible cloud endpoint, including Alibaba
Bailian/Qwen) are optional and configured through environment variables such as
`CASCADE_SMALL_BASE_URL`, `CASCADE_FRONTIER_BASE_URL` and `DASHSCOPE_API_KEY`.
The offline judge uses `CASCADE_JUDGE_BASE_URL` / `CASCADE_JUDGE_API_KEY` /
`CASCADE_JUDGE_MODEL` and falls back to the DashScope key. Never commit
endpoints or keys; see the README for setup.

## 6. End-of-Session Checklist

- [ ] `./init.sh` verification still passes.
- [ ] Harness state under `private/` reflects the true state (no false `passing`).
- [ ] The session log records the handoff, including any blocker.
