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
console.log("web metrics match the Python ledger");
