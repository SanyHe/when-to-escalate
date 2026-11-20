// Verify that the browser metric formulas match the Python ledger exactly.
//
// Usage (repo root):
//   node cascade/tests/verify_web_metrics.js
//
// Exits non-zero when web/js/metrics.js disagrees with the committed
// web/data/ledger.json, which is what the deploy workflow checks.

"use strict";

const path = require("path");
const ledger = require(path.join(__dirname, "..", "..", "web", "data", "ledger.json"));
const metrics = require(path.join(__dirname, "..", "..", "web", "js", "metrics.js"));

// The panel's real-results view reads this file; a missing or malformed copy
// would silently show an empty panel, so fail the deploy check loudly.
const realPath = path.join(__dirname, "..", "..", "web", "data", "real_summary.json");
let real = null;
try {
  real = require(realPath);
} catch (e) {
  console.error(`real summary missing or unreadable: ${realPath} (${e.message})`);
  console.error("Rebuild it with: python3 cascade/src/build_web_real.py");
  process.exit(1);
}

const params = metrics.defaultParams(ledger);
const computed = metrics.computeAll(ledger, params);

const CHECKS = [
  { key: "total_cost_usd", tolerance: 1e-9 },
  { key: "cpst_usd", tolerance: 1e-9 },
  { key: "success_rate", tolerance: 1e-6 },
  { key: "escalation_rate", tolerance: 1e-6 },
  { key: "avg_latency_ms", tolerance: 0.1 },
  { key: "avg_attempts", tolerance: 1e-4 },
  { key: "savings_vs_frontier", tolerance: 1e-6 },
];

let failures = 0;

console.log(`ledger mode: ${ledger._meta.mode} | tasks: ${ledger._meta.task_count}`);

metrics.POLICIES.forEach((policy) => {
  const expected = ledger.metrics[policy];
  const actual = computed[policy];
  let ok = true;
  for (const check of CHECKS) {
    const diff = Math.abs(Number(expected[check.key]) - Number(actual[check.key]));
    if (diff > check.tolerance) {
      ok = false;
      failures += 1;
      console.error(
        `  ${policy}.${check.key}: python=${expected[check.key]} js=${actual[check.key]} diff=${diff}`
      );
    }
  }
  console.log(
    `  ${policy.padEnd(12)} ${ok ? "OK" : "FAIL"} ` +
      `cost=${actual.total_cost_usd.toFixed(6)} cpst=${actual.cpst_usd.toFixed(6)} ` +
      `success=${(actual.success_rate * 100).toFixed(1)}% ` +
      `escalation=${(actual.escalation_rate * 100).toFixed(1)}% ` +
      `savings=${(actual.savings_vs_frontier * 100).toFixed(1)}%`
  );
});

if (failures) {
  console.error(`web metrics mismatch: ${failures} checks failed`);
  process.exit(1);
}

// --- real_summary.json sanity: single source of truth for the panel's real view ---
let realFailures = 0;
function realCheck(cond, msg) {
  if (!cond) { realFailures += 1; console.error(`  real: ${msg}`); }
}
const rm = real._meta || {};
realCheck(rm.mode === "real_measured", `_meta.mode must be real_measured, got ${rm.mode}`);
realCheck(Array.isArray(real.runs) && real.runs.length === 3, "runs must be length 3");
realCheck(!!real.mean && !!real.headline, "mean and headline required");
for (const p of ["all_frontier", "cascade", "all_small"]) {
  const m = real.mean && real.mean[p];
  realCheck(!!m && typeof m.success_rate === "number" && m.success_rate >= 0 && m.success_rate <= 1, `${p}.success_rate out of range`);
  realCheck(!!m && typeof m.cpst_usd === "number" && m.cpst_usd >= 0, `${p}.cpst_usd negative`);
}
realCheck(rm.judge_model === "external-non-qwen-judge", `judge_model must use the neutral public label, got ${rm.judge_model}`);
realCheck(real.headline.cascade_cost_pct_of_frontier > 0 && real.headline.cascade_cost_pct_of_frontier < 100, "headline cost pct out of range");
if (realFailures) {
  console.error(`real summary invalid: ${realFailures} checks failed`);
  process.exit(1);
}
const h = real.headline;
console.log(`real summary OK: ${rm.runs}-run mean | cascade ${(h.cascade_success * 100).toFixed(1)}% vs frontier ${(h.frontier_success * 100).toFixed(1)}% | cost ${h.cascade_cost_pct_of_frontier.toFixed(1)}% of frontier | judge ${rm.judge_model}`);
console.log("web metrics match the Python ledger");
