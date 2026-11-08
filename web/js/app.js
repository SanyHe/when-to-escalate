// Cost panel for the When-to-Escalate demo.
//
// Pure static JS: loads data/ledger.json (task prompts, router confidence and
// the raw per-attempt mock responses), then re-simulates all three policies in
// the browser. Metric math lives in js/metrics.js, which is also verified
// against the Python ledger by cascade/tests/verify_web_metrics.js.
//
// All user-facing strings come from js/i18n.js, so the page can switch between
// Chinese and English at runtime. Live gateway mode is optional (js/remote.js);
// the offline mock ledger is always available.

(function () {
  "use strict";

  var metricsApi = window.WTEMetrics;
  var i18n = window.WTEI18n;
  var remote = window.WTEMote;

  var state = {
    ledger: null,
    params: null,
    defaults: null,
    policy: "cascade",
    filter: "all",
    loadError: null,
    liveEnabled: false,
  };

  function t(key, vars) { return i18n.t(key, vars); }
  function el(id) { return document.getElementById(id); }
  function policyLabel(name) { return i18n.label("policy", name); }
  function modelLabel(name) { return i18n.label("model", name); }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatPct(value, digits) {
    if (typeof value !== "number" || isNaN(value)) return "—";
    return (value * 100).toFixed(digits == null ? 1 : digits) + "%";
  }

  function formatUsd(value) {
    if (typeof value !== "number" || isNaN(value)) return "—";
    return "$" + value.toFixed(6);
  }

  function formatMs(value) {
    if (typeof value !== "number" || isNaN(value)) return "—";
    return Math.round(value) + " ms";
  }

  function cloneParams(params) {
    return JSON.parse(JSON.stringify(params));
  }

  // ---------------------------------------------------------------------
  // Static chrome
  // ---------------------------------------------------------------------
  function renderPolicyTabs() {
    var container = el("policySwitch");
    container.innerHTML = "";
    metricsApi.POLICIES.forEach(function (name) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "model-tab" + (name === state.policy ? " active" : "");
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", name === state.policy ? "true" : "false");
      button.innerHTML =
        '<span class="tab-label">' + escapeHtml(policyLabel(name)) + "</span>" +
        '<span class="tab-tag">' + escapeHtml(t("policy." + name + ".tag")) + "</span>";
      button.addEventListener("click", function () { switchPolicy(name); });
      container.appendChild(button);
    });
  }

  function switchPolicy(name) {
    if (name === state.policy) return;
    state.policy = name;
    renderPolicyTabs();
    renderMetrics();
    renderTaskList();
    renderCompare();
  }

  function renderFilterBar() {
    Array.prototype.forEach.call(el("filterBar").querySelectorAll("button"), function (button) {
      var filter = button.getAttribute("data-filter");
      button.className = "btn" + (filter === state.filter ? " btn-primary" : "");
    });
  }

  function applyModeChrome() {
    if (!state.ledger) return;
    var meta = state.ledger._meta;
    var isMock = meta.mode === "mock";
    var badge = el("modeBadge");
    badge.textContent = isMock ? t("badge.mock") : t("badge.real");
    badge.title = meta.note || t("badge.mockTitle");
    badge.classList.toggle("badge-mock", isMock);
    badge.classList.toggle("badge-ok", !isMock);
    el("replaySub").textContent = t("replay.sub", { total: meta.task_count });
  }

  // ---------------------------------------------------------------------
  // Metrics
  // ---------------------------------------------------------------------
  function computeAll() {
    if (!state.ledger || !state.params) return null;
    return metricsApi.computeAll(state.ledger, state.params);
  }

  function metricTile(label, value, cls) {
    return '<div class="metric ' + (cls || "") + '">' +
      '<div class="m-label">' + escapeHtml(label) + "</div>" +
      '<div class="m-value">' + escapeHtml(value) + "</div>" +
      "</div>";
  }

  function renderMetrics() {
    var computed = computeAll();
    var grid = el("metricGrid");
    if (!computed) {
      grid.innerHTML = metricTile(t("metric.totalCost"), "—", "") +
        metricTile(t("metric.cpst"), "—", "") +
        metricTile(t("metric.success"), "—", "") +
        metricTile(t("metric.escalation"), "—", "") +
        metricTile(t("metric.latency"), "—", "") +
        metricTile(t("metric.savings"), "—", "");
      return;
    }
    var m = computed[state.policy];
    var successClass = m.success_rate >= 0.95 ? "good" : (m.success_rate >= 0.9 ? "warn" : "bad");
    var savingsClass = m.savings_vs_frontier >= 0.3 ? "good" : (m.savings_vs_frontier > 0 ? "warn" : "");
    grid.innerHTML =
      metricTile(t("metric.totalCost"), formatUsd(m.total_cost_usd), "") +
      metricTile(t("metric.cpst"), formatUsd(m.cpst_usd), "") +
      metricTile(t("metric.success"), formatPct(m.success_rate), successClass) +
      metricTile(t("metric.escalation"), formatPct(m.escalation_rate), "") +
      metricTile(t("metric.latency"), formatMs(m.avg_latency_ms), "") +
      metricTile(t("metric.savings"), formatPct(m.savings_vs_frontier), savingsClass);
    el("metricsSub").textContent = t("metrics.sub") + " · " + policyLabel(state.policy);
  }

  function renderCompare() {
    var computed = computeAll();
    var container = el("compareGrid");
    if (!computed) { container.innerHTML = ""; return; }
    container.innerHTML = metricsApi.POLICIES.map(function (name) {
      var m = computed[name];
      var active = name === state.policy;
      return '<div class="compare-card' + (active ? " active" : "") + '">' +
        '<div class="c-head">' +
          '<div><div class="c-label">' + escapeHtml(policyLabel(name)) + "</div>" +
          '<div class="c-sub">' + escapeHtml(active ? t("compare.active") : t("policy." + name + ".tag")) + "</div></div>" +
          '<div class="c-savings">' + formatPct(m.savings_vs_frontier) + "</div>" +
        "</div>" +
        '<div class="c-row c-headline"><span>' + escapeHtml(t("compare.total")) + "</span><b>" +
          escapeHtml(formatUsd(m.total_cost_usd)) + "</b></div>" +
        '<div class="c-row"><span>' + escapeHtml(t("compare.cpst")) + "</span><b>" +
          escapeHtml(formatUsd(m.cpst_usd)) + "</b></div>" +
        '<div class="c-row"><span>' + escapeHtml(t("compare.success")) + "</span><b>" +
          formatPct(m.success_rate) + "</b></div>" +
        "</div>";
    }).join("");
  }

  // ---------------------------------------------------------------------
  // Parameters
  // ---------------------------------------------------------------------
  var PARAMS = [
    { key: "threshold", label: "params.threshold", min: 0.30, max: 0.95, step: 0.01, digits: 2 },
    { key: "pricing.small.input", label: "params.smallInput", min: 0, max: 1, step: 0.01, digits: 2 },
    { key: "pricing.small.output", label: "params.smallOutput", min: 0, max: 3, step: 0.01, digits: 2 },
    { key: "pricing.frontier.input", label: "params.frontierInput", min: 0, max: 10, step: 0.1, digits: 1 },
    { key: "pricing.frontier.output", label: "params.frontierOutput", min: 0, max: 30, step: 0.1, digits: 1 },
    { key: "weights.simple", label: "params.simple", min: 0, max: 3, step: 0.1, digits: 1 },
    { key: "weights.medium", label: "params.medium", min: 0, max: 3, step: 0.1, digits: 1 },
    { key: "weights.complex", label: "params.complex", min: 0, max: 3, step: 0.1, digits: 1 }
  ];

  function getParam(key) {
    var parts = key.split(".");
    var node = state.params;
    for (var i = 0; i < parts.length; i += 1) node = node[parts[i]];
    return Number(node);
  }

  function setParam(key, value) {
    var parts = key.split(".");
    var node = state.params;
    for (var i = 0; i < parts.length - 1; i += 1) node = node[parts[i]];
    node[parts[parts.length - 1]] = Number(value);
  }

  function renderParams() {
    var grid = el("paramGrid");
    grid.innerHTML = PARAMS.map(function (spec) {
      var value = getParam(spec.key);
      return '<div class="param" data-param="' + spec.key + '">' +
        '<div class="param-head"><span>' + escapeHtml(t(spec.label)) + "</span>" +
        '<b>' + value.toFixed(spec.digits) + "</b></div>" +
        '<input type="range" min="' + spec.min + '" max="' + spec.max + '" step="' +
        spec.step + '" value="' + value + '" aria-label="' + escapeHtml(t(spec.label)) + '">' +
        "</div>";
    }).join("");

    Array.prototype.forEach.call(grid.querySelectorAll(".param"), function (row) {
      var key = row.getAttribute("data-param");
      var input = row.querySelector("input");
      var display = row.querySelector("b");
      input.addEventListener("input", function () {
        setParam(key, input.value);
        var spec = PARAMS.filter(function (p) { return p.key === key; })[0];
        display.textContent = Number(input.value).toFixed(spec.digits);
        renderMetrics();
        renderCompare();
        renderTaskList();
      });
    });
  }

  function resetParams() {
    state.params = cloneParams(state.defaults);
    renderParams();
    renderMetrics();
    renderCompare();
    renderTaskList();
  }

  // ---------------------------------------------------------------------
  // Per-task routing chain
  // ---------------------------------------------------------------------
  function reasonText(entry, sim) {
    if (state.policy === "all_frontier") return t("task.frontierOnly");
    if (state.policy === "all_small") {
      return sim.attempts > 1 ? t("task.smallRetry") : t("task.allSmallOnly");
    }
    if (!sim.escalated) {
      return t("task.kept");
    }
    if (sim.responses[0] && !sim.responses[0].success) {
      return t("task.escalateFail");
    }
    return t("task.escalateConf", {
      c: formatPct(entry.confidence, 1),
      t: formatPct(state.params.threshold, 0),
    });
  }

  function chainChip(response) {
    var role = response.model;
    var cls = role === "frontier" ? "frontier" : "small";
    var stateCls = response.success ? "ok" : "fail";
    var mark = response.success ? "✓" : "✕";
    return '<span class="model-chip ' + cls + " " + stateCls + '">' +
      escapeHtml(modelLabel(role)) + " " + mark + "</span>";
  }

  function taskItem(entry, sim) {
    var task = entry.task;
    var statusCls = sim.success ? "ok" : "fail";
    var statusText = sim.success ? t("task.success") : t("task.failed");
    var chain = sim.responses.map(chainChip).join('<span class="arrow">→</span>');
    var escalatedBadge = sim.escalated
      ? '<span class="pill pill-escalated">' + escapeHtml(t("task.escalated")) + "</span>"
      : "";
    return '<div class="task-item ' + statusCls + (sim.escalated ? " escalated" : "") + '">' +
      '<div class="task-head">' +
        '<span class="task-id">' + escapeHtml(task.task_id) + "</span>" +
        '<span class="pill pill-kind ' + escapeHtml(task.kind) + '">' +
          escapeHtml(i18n.label("kind", task.kind)) + "</span>" +
        '<span class="pill pill-difficulty">' +
          escapeHtml(i18n.label("difficulty", task.expected_difficulty)) + "</span>" +
        escalatedBadge +
        '<span class="task-status ' + statusCls + '">' + escapeHtml(statusText) + "</span>" +
      "</div>" +
      '<div class="task-prompt">' + escapeHtml(task.prompt) + "</div>" +
      '<div class="task-chain">' + chain + "</div>" +
      '<div class="task-meta">' +
        "<span>" + escapeHtml(t("task.confidence", { value: formatPct(entry.confidence, 1) })) + "</span>" +
        "<span>" + escapeHtml(t("task.cost", { value: sim.cost.toFixed(6) })) + "</span>" +
        "<span>" + escapeHtml(t("task.attempts", { n: sim.attempts })) + "</span>" +
      "</div>" +
      '<div class="task-reason">' + escapeHtml(reasonText(entry, sim)) + "</div>" +
      "</div>";
  }

  function renderTaskList() {
    var list = el("taskList");
    if (!state.ledger || !state.params) {
      list.innerHTML = '<div class="list-empty">' +
        escapeHtml(state.loadError ? t("banner.loadFail", { error: state.loadError }) : t("task.empty")) +
        "</div>";
      el("taskCounter").textContent = "0 / 0";
      return;
    }
    var shown = [];
    state.ledger.tasks.forEach(function (entry) {
      var sim = metricsApi.simulateTask(entry, state.policy, state.params);
      if (state.filter === "escalated" && !sim.escalated) return;
      if (state.filter === "failed" && sim.success) return;
      shown.push({ entry: entry, sim: sim });
    });
    if (!shown.length) {
      list.innerHTML = '<div class="list-empty">' + escapeHtml(t("task.empty")) + "</div>";
    } else {
      list.innerHTML = shown.map(function (row) {
        return taskItem(row.entry, row.sim);
      }).join("");
    }
    el("taskCounter").textContent = t("replay.count", {
      shown: shown.length,
      total: state.ledger._meta.task_count,
    });
    el("replaySub").textContent = t("replay.sub", {
      total: state.ledger._meta.task_count,
    });
  }

  // ---------------------------------------------------------------------
  // Online gateway mode
  // ---------------------------------------------------------------------
  function setLiveMsg(text, isError) {
    var msg = el("liveMsg");
    msg.textContent = text;
    msg.classList.toggle("live-error", !!isError);
  }

  function renderLiveBadge() {
    var badge = el("liveBadge");
    badge.classList.remove("badge-ok", "badge-bad");
    badge.textContent = state.liveEnabled ? t("live.badgeOn") : t("live.badgeOff");
    badge.classList.add(state.liveEnabled ? "badge-ok" : "badge-bad");
    el("liveSave").textContent = state.liveEnabled ? t("live.disable") : t("live.enable");
    el("liveRun").classList.toggle("hidden", !state.liveEnabled);
  }

  function fillLiveForm() {
    var cfg = remote.getConfig();
    el("liveBase").value = cfg.baseUrl || "";
  }

  function renderLiveResult(result, error) {
    var box = el("liveResult");
    if (error) {
      box.innerHTML = '<div class="live-error-text">' +
        escapeHtml(t("live.fallback", { error: error })) + "</div>";
      box.classList.remove("hidden");
      return;
    }
    var cascade = result.cascade;
    var facts = "";
    if (cascade) {
      facts = '<div class="live-facts">' +
        "<span>" + escapeHtml(t("live.policy")) + ": " + escapeHtml(cascade.policy) + "</span>" +
        "<span>" + escapeHtml(t("live.cost")) + ": " + formatUsd(cascade.cost_usd) + "</span>" +
        "<span>" + escapeHtml(t("live.attempts")) + ": " + cascade.attempts + "</span>" +
        "<span>" + escapeHtml(t("live.escalated")) + ": " +
          (cascade.escalated ? "yes" : "no") + "</span>" +
        "<span>" + escapeHtml(t("live.confidence")) + ": " +
          formatPct(cascade.confidence, 1) + "</span>" +
        "<span>" + escapeHtml(t("live.latency")) + ": " +
          formatMs(cascade.latency_ms) + "</span>" +
        "</div>";
    }
    box.innerHTML = '<div class="live-result-head">' + escapeHtml(t("live.resultTitle")) + "</div>" +
      '<div class="live-answer">' + escapeHtml(result.content || "—") + "</div>" +
      facts;
    box.classList.remove("hidden");
  }

  function applyLive(enabled) {
    var baseUrl = el("liveBase").value.trim();
    if (!enabled) {
      remote.saveConfig({ baseUrl: baseUrl, enabled: false });
      state.liveEnabled = false;
      renderLiveBadge();
      setLiveMsg(t("live.hint"), false);
      el("liveResult").classList.add("hidden");
      return;
    }
    if (!baseUrl) {
      setLiveMsg(t("live.needBase"), true);
      return;
    }
    // Only go LIVE after a successful health check, so "LIVE" really means
    // the panel can reach the gateway.
    remote.saveConfig({ baseUrl: baseUrl, enabled: false });
    setLiveMsg(t("live.testing"), false);
    el("liveSave").disabled = true;
    remote.ping().then(function (info) {
      remote.saveConfig({ baseUrl: baseUrl, enabled: true });
      state.liveEnabled = true;
      renderLiveBadge();
      setLiveMsg(t("live.testOk", {
        policy: info.policy,
        backends: info.backends,
      }), false);
    }).catch(function (error) {
      state.liveEnabled = false;
      renderLiveBadge();
      setLiveMsg(t("live.testFail", { error: error.message }), true);
    }).then(function () {
      el("liveSave").disabled = false;
    });
  }

  function bindLivePanel() {
    fillLiveForm();
    state.liveEnabled = remote.isEnabled();
    renderLiveBadge();
    setLiveMsg(t("live.hint"), false);

    el("liveTest").addEventListener("click", function () {
      var baseUrl = el("liveBase").value.trim();
      if (!baseUrl) {
        setLiveMsg(t("live.needBase"), true);
        return;
      }
      remote.saveConfig({ baseUrl: baseUrl, enabled: state.liveEnabled });
      setLiveMsg(t("live.testing"), false);
      remote.ping().then(function (info) {
        setLiveMsg(t("live.testOk", {
          policy: info.policy,
          backends: info.backends,
        }), false);
      }).catch(function (error) {
        setLiveMsg(t("live.testFail", { error: error.message }), true);
      });
    });

    el("liveSave").addEventListener("click", function () {
      applyLive(!state.liveEnabled);
    });

    el("liveRunBtn").addEventListener("click", function () {
      var prompt = el("livePrompt").value.trim();
      if (!prompt) return;
      setLiveMsg(t("live.running"), false);
      el("liveRunBtn").disabled = true;
      remote.complete(prompt).then(function (result) {
        renderLiveResult(result, null);
        setLiveMsg(t("live.hint"), false);
      }).catch(function (error) {
        renderLiveResult(null, error.message);
        setLiveMsg(t("live.fallback", { error: error.message }), true);
      }).then(function () {
        el("liveRunBtn").disabled = false;
      });
    });
  }

  // ---------------------------------------------------------------------
  // Load + localisation
  // ---------------------------------------------------------------------
  function renderBanner() {
    var banner = el("banner");
    if (state.loadError) {
      banner.innerHTML = t("banner.loadFail", { error: escapeHtml(state.loadError) });
      banner.classList.remove("hidden");
    } else {
      banner.innerHTML = "";
      banner.classList.add("hidden");
    }
  }

  function relocalize() {
    i18n.applyDom();
    renderPolicyTabs();
    renderFilterBar();
    renderLiveBadge();
    renderBanner();
    applyModeChrome();
    renderMetrics();
    renderParams();
    renderTaskList();
    renderCompare();
  }

  function init() {
    i18n.applyDom();
    renderPolicyTabs();
    renderFilterBar();
    renderMetrics();
    bindLivePanel();

    el("langBtn").addEventListener("click", function () {
      i18n.setLang(i18n.getLang() === "zh" ? "en" : "zh");
    });
    i18n.onChange(relocalize);

    Array.prototype.forEach.call(el("filterBar").querySelectorAll("button"), function (button) {
      button.addEventListener("click", function () {
        state.filter = button.getAttribute("data-filter");
        renderFilterBar();
        renderTaskList();
      });
    });
    el("resetParams").addEventListener("click", resetParams);

    fetch("data/ledger.json")
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (ledger) {
        state.ledger = ledger;
        state.defaults = metricsApi.defaultParams(ledger);
        state.params = cloneParams(state.defaults);
        applyModeChrome();
        renderParams();
        renderMetrics();
        renderTaskList();
        renderCompare();
      })
      .catch(function (error) {
        if (window.console && error) {
          console.error("WTE panel failed:", error.stack || error);
        }
        state.loadError = error.message;
        renderBanner();
        renderTaskList();
      });

    // Exposed for debugging and the node verification check.
    window.WTE = {
      state: state,
      computeAll: computeAll,
      simulateTask: metricsApi.simulateTask,
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
