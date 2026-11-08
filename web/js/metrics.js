// Shared cascade metrics for the When-to-Escalate cost panel.
//
// This is the single JS source of truth for the three-policy economics. It
// mirrors cascade/src/replay.py + engine.py exactly so the browser panel and
// the offline ledger cannot drift apart.
//
// Usable from the browser (window.WTEMetrics) and from node (module.exports),
// which lets the build verify web/data/ledger.json against the Python ledger.
//
// Policies:
//   all_frontier  one frontier attempt per task
//   all_small     small attempt, one retry on failure
//   cascade       small first; frontier when the small call fails or when the
//                 router confidence is below the threshold
//
// Every attempt's cost is included, so retry and escalation spend shows up in
// CPST (Cost per Successful Task), just like the Python engine.

(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.WTEMetrics = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var POLICIES = ["all_frontier", "cascade", "all_small"];
  var KINDS = ["simple", "medium", "complex"];
  var TOKENS_PER_UNIT = 1000000;

  function round(value, digits) {
    var factor = Math.pow(10, digits);
    return Math.round((value + Number.EPSILON) * factor) / factor;
  }

  function safeDiv(numerator, denominator) {
    return denominator ? numerator / denominator : 0;
  }

  function callCost(response, pricing) {
    var prices = pricing[response.model];
    if (!prices) return 0;
    return round(
      response.usage.prompt_tokens / TOKENS_PER_UNIT * prices.input +
        response.usage.completion_tokens / TOKENS_PER_UNIT * prices.output,
      9
    );
  }

  function defaultParams(ledger) {
    var meta = ledger._meta;
    var pricing = {};
    Object.keys(meta.pricing).forEach(function (model) {
      pricing[model] = {
        input: Number(meta.pricing[model].input),
        output: Number(meta.pricing[model].output),
      };
    });
    var weights = {};
    KINDS.forEach(function (kind) { weights[kind] = 1; });
    return {
      threshold: Number(meta.policy.confidence_threshold),
      pricing: pricing,
      weights: weights,
    };
  }

  // Simulate one task under one policy and the current parameter set.
  function simulateTask(entry, policy, params) {
    var small = entry.attempts.small || [];
    var frontier = entry.attempts.frontier || [];
    var used = [];
    var escalated = false;

    if (policy === "all_frontier") {
      if (frontier[0]) used.push(frontier[0]);
    } else if (policy === "all_small") {
      if (small[0]) used.push(small[0]);
      if (small[0] && !small[0].success && small[1]) used.push(small[1]);
    } else {
      if (small[0]) used.push(small[0]);
      escalated = !small[0] || !small[0].success ||
        entry.confidence < params.threshold;
      if (escalated && frontier[0]) used.push(frontier[0]);
    }

    var cost = 0;
    var latency = 0;
    used.forEach(function (response) {
      cost += callCost(response, params.pricing);
      latency += Number(response.latency_ms || 0);
    });
    var success = used.some(function (response) { return response.success; });

    return {
      cost: round(cost, 9),
      latency: latency,
      attempts: used.length,
      success: success,
      escalated: escalated,
      responses: used,
    };
  }

  function compute(ledger, policy, params) {
    var totalWeight = 0;
    var totalCost = 0;
    var successWeight = 0;
    var successCost = 0;
    var escalatedWeight = 0;
    var latencyWeighted = 0;
    var attemptsWeighted = 0;
    var failedCost = 0;

    ledger.tasks.forEach(function (entry) {
      var weight = Number(params.weights[entry.task.kind] || 0);
      if (weight <= 0) return;
      var sim = simulateTask(entry, policy, params);
      totalWeight += weight;
      totalCost += weight * sim.cost;
      latencyWeighted += weight * sim.latency;
      attemptsWeighted += weight * sim.attempts;
      if (sim.success) {
        successWeight += weight;
        successCost += weight * sim.cost;
      } else {
        failedCost += weight * sim.cost;
      }
      if (sim.escalated) escalatedWeight += weight;
    });

    return {
      policy: policy,
      tasks: totalWeight,
      total_cost_usd: round(totalCost, 9),
      cpst_usd: round(safeDiv(successCost, successWeight), 9),
      success_rate: round(safeDiv(successWeight, totalWeight), 6),
      escalation_rate: round(safeDiv(escalatedWeight, totalWeight), 6),
      avg_latency_ms: round(safeDiv(latencyWeighted, totalWeight), 1),
      avg_attempts: round(safeDiv(attemptsWeighted, totalWeight), 4),
      failed_cost_usd: round(failedCost, 9),
      weighted_tasks: round(totalWeight, 4),
      savings_vs_frontier: 0,
    };
  }

  function computeAll(ledger, params) {
    var out = {};
    POLICIES.forEach(function (policy) {
      out[policy] = compute(ledger, policy, params);
    });
    var reference = out.all_frontier.total_cost_usd;
    POLICIES.forEach(function (policy) {
      out[policy].savings_vs_frontier = reference > 0
        ? round(1 - out[policy].total_cost_usd / reference, 6)
        : 0;
    });
    return out;
  }

  return {
    POLICIES: POLICIES,
    KINDS: KINDS,
    defaultParams: defaultParams,
    simulateTask: simulateTask,
    callCost: callCost,
    compute: compute,
    computeAll: computeAll,
  };
});
