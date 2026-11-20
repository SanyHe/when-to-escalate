# 01 · Why Cascade Inference

> Series: When to Speak → **When to Escalate**. The first asks *when should it speak*; this one asks *when should it pay for a bigger model*.

## 1. The problem is unit economics, not model quality

By 2026, inference cost is a product-level constraint for an always-on agent, not an implementation detail. An always-on agent does not field one query at a time — it runs a steady stream of decision points: filtering notifications, reading the weather, drafting a reply, setting a reminder, and occasionally sending a message or moving money. Most of these are cheap and reversible; a few are expensive and irreversible. Sending every one of them to the most expensive model may maximise quality, but it destroys unit economics first. The recurring conclusion in industry reports is that cost is a **routing problem**: pay for the frontier model only for the decisions that actually need it.

Cascade inference makes a simple bet:

- most tasks do not need a frontier model;
- when the small model is wrong, we can often tell (failure, timeout, low confidence);
- so let the small model try first, and pay for the frontier model only when the task is uncertain.

Perplexity's Portable Computer, RouteLLM's routing experiments and LiteLLM's fallback chains all express the same idea: **not every task deserves the most expensive model**.

## 2. Three architectures on one task flow

| Policy | Behaviour | Intuition | Typical failure |
|---|---|---|---|
| `all_frontier` | every task goes to the frontier | simple, high success | expensive; heavy users erode gross margin |
| `cascade` | small first, escalate on failure or low confidence | pay on demand | needs a trustworthy escalation signal |
| `all_small` | every task stays on the small model | cheapest per call | complex tasks fail, and retries still cost money |

Looking only at per-call price gives the wrong answer:

- all-frontier has a high unit price but no retry waste;
- all-small has a tiny unit price but failure cost is spread over the successful tasks;
- cascade pays both small and some frontier calls, but only for the tasks that actually need them.

That is why the north-star metric here is **Cost per Successful Task (CPST)**: total cost of successful tasks divided by successful tasks, with retry and escalation spend included.

## 3. What this project tries to prove

This is a runnable product prototype, not an opinion piece. It aims to show four things:

1. **Routing and accounting can be pure functions.** Given a task, prices and a policy, cost, confidence and the escalation chain are reproducible without a GPU or an online service.
2. **Cascade can cut cost without sacrificing success.** On 100 synthetic tasks and illustrative prices, the mock ledger saves about **49.87%** versus all-frontier while success rises from 98% to 99%.
3. **An always-on agent can route by consequence, not just by difficulty.** The personal policy layer buckets each decision point by consequence / latency / load and applies hard constraints, so irreversible actions never ride on the cheap model and low-stakes sensing never pays for the frontier one — independent of the cascade engine (see [02-method.md](02-method.md)).
4. **Unit economics can become an interactive product surface.** The panel switches policies, adjusts threshold and prices, shows each task's escalation reason, and can optionally connect to a real gateway.

It deliberately does **not** prove:

- that the policy layer is already live — it is offline and simulated today, and is not wired into the gateway (see [02-method.md](02-method.md));
- "same success, cheaper" on real models — real cost/quality conclusions are model- and operating-point-dependent; F2.5 passes only under a revised trade-off criterion (about 37% of frontier cost for a 4 pp success loss), see [03-eval.md](03-eval.md);
- the value of a learned router (this iteration uses a deterministic rule);
- any vendor's real price list (the pricing table is illustrative).

## 4. Design principles

- **Mock first, real optional.** The ledger, gateway tests and static panel work without a GPU or API key.
- **Determinism.** Fixed seeds, stable hashes, pure functions; same input, same output.
- **Every attempt is billed.** Failure, retry and escalation are never "free"; they enter CPST.
- **One source of truth.** Python and the browser share the same formulas, enforced by `verify_web_metrics.js`.
- **Zero-secret delivery.** Endpoints and keys are environment-only; the static site makes no network requests by default.

## 5. Relationship to When to Speak

Both projects share the same Harness Engineering workflow:

- `AGENTS.md` / `harness.yaml` / `init.sh` define how a session starts and how work is verified;
- `private/` holds local state (gitignored), while the public repo only contains reviewable feature lists, progress and docs;
- strict M1 → M2 → M3 order, one feature at a time, evidence required before a feature is marked passing.

Narratively, When to Speak is about *interaction timing*; When to Escalate is about *compute tiers*. Both are infrastructure questions for Personal AI / always-on agents.

## 6. References

- Morgan Stanley Research, *23 Days of Musing… Top Investor Questions and Our Answers* (2026-09-30)
- Menlo Ventures, *2026: The State of Enterprise AI* (2026-11-03)
- RouteLLM (LMSYS, arXiv:2406.18665, ICLR 2025)
- Perplexity Portable Computer product documentation (2026-08-25)
- Previous project: [`when-to-speak`](https://github.com/SanyHe/when-to-speak)

> Verify figures against the primary source on the day you quote them; this article does not treat second-hand summaries as ground truth.
