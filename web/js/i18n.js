// Bilingual UI strings for the When-to-Escalate cost panel (Chinese / English).
//
// Exposes window.WTEI18n:
//   t(key, vars)        translate a key, replacing {name} placeholders
//   getLang()           current language code ("zh" | "en")
//   setLang(lang)       switch language, persist it, notify listeners
//   onChange(fn)        subscribe to language changes
//   applyDom(root)      refresh static text marked with data-i18n attributes
//
// Static markup uses data-i18n (textContent), data-i18n-html (innerHTML for
// strings that contain <code>), and data-i18n-title (title attribute).
// Dynamically rendered panels are re-rendered by app.js on every change.

(function (root) {
  "use strict";

  var DICT = {
    zh: {
      "app.title": "When to Escalate — 何时该升级",
      "app.desc": "级联推理成本面板：小模型先做，低置信或失败才升级旗舰模型，实时比较三种架构的单位经济。",
      "brand.sub": "cascade inference demo · 何时该升级",
      "badge.mock": "MOCK LEDGER",
      "badge.real": "REAL LEDGER",
      "badge.mockTitle": "当前展示的是确定性 mock 账本，不是实测模型输出；真实评测见 F2.5。",
      "lang.switch": "切换到英文",
      "lang.button": "EN",

      "hero.title": "什么时候该升级到旗舰模型？",
      "hero.body": "同一个任务流分别交给三种架构：全旗舰、智能级联、全小模型。级联先让小模型作答，只有失败或置信度低于阈值时才升级旗舰，并把每一次尝试的成本都计入 <code>CPST</code>（Cost per Successful Task）。切换策略、拖动参数，实时看单位经济如何变化。",
      "hero.switchAria": "策略切换",

      "policy.all_frontier": "全旗舰",
      "policy.all_frontier.tag": "all_frontier",
      "policy.cascade": "智能级联",
      "policy.cascade.tag": "cascade · 推荐",
      "policy.all_small": "全小模型",
      "policy.all_small.tag": "all_small",

      "banner.loadFail": "<b>无法加载账本 web/data/ledger.json：</b> {error}。请先运行 python3 cascade/src/replay.py 重新生成。",

      "replay.title": "逐任务路由链",
      "replay.sub": "确定性 mock 账本 · {total} 条任务",
      "replay.count": "{shown} / {total} 条",
      "filter.all": "全部",
      "filter.escalated": "仅升级",
      "filter.failed": "仅失败",
      "task.empty": "当前筛选条件下没有任务。",
      "task.confidence": "置信度 {value}",
      "task.cost": "成本 ${value}",
      "task.attempts": "{n} 次尝试",
      "task.escalated": "已升级",
      "task.success": "成功",
      "task.failed": "失败",
      "task.startReason": "小模型先作答",
      "task.escalateFail": "小模型失败 → 升级旗舰",
      "task.escalateConf": "置信度 {c} 低于阈值 {t} → 升级旗舰",
      "task.kept": "置信度达标，保留小模型结果",
      "task.frontierOnly": "策略要求：直接走旗舰模型",
      "task.allSmallOnly": "策略要求：只使用小模型",
      "task.smallRetry": "小模型失败 → 重试小模型",
      "task.chainSmall": "小模型",
      "task.chainFrontier": "旗舰",

      "kind.simple": "简单",
      "kind.medium": "中等",
      "kind.complex": "复杂",
      "difficulty.low": "低难度",
      "difficulty.medium": "中难度",
      "difficulty.high": "高难度",
      "model.small": "小模型",
      "model.frontier": "旗舰模型",

      "metrics.title": "实时指标",
      "metrics.sub": "随策略与参数实时重算 · mock",
      "metric.totalCost": "总成本",
      "metric.cpst": "CPST",
      "metric.success": "成功率",
      "metric.escalation": "升级率",
      "metric.latency": "平均延迟",
      "metric.savings": "相对全旗舰节省",
      "metric.failedCost": "失败任务浪费",

      "compare.title": "三策略对比",
      "compare.sub": "同一任务流 · 同一套参数 · mock 值",
      "compare.total": "总成本",
      "compare.cpst": "CPST",
      "compare.success": "成功率",
      "compare.active": "当前策略",

      "params.title": "可调参数",
      "params.sub": "阈值、单价与流量混合会实时重算单位经济",
      "params.reset": "恢复默认",
      "params.mockNote": "示例定价与 mock 轨迹仅用于演示口径，不代表任何厂商报价。",
      "params.threshold": "置信度阈值",
      "params.smallInput": "小模型输入价 / 1M tokens",
      "params.smallOutput": "小模型输出价 / 1M tokens",
      "params.frontierInput": "旗舰输入价 / 1M tokens",
      "params.frontierOutput": "旗舰输出价 / 1M tokens",
      "params.mix": "流量混合权重",
      "params.simple": "简单任务",
      "params.medium": "中等任务",
      "params.complex": "复杂任务",

      "live.title": "在线模式（自托管网关）",
      "live.sub": "连接 OpenAI 兼容的级联网关，用真实请求验证路由与成本",
      "live.badgeOn": "LIVE",
      "live.badgeOff": "OFFLINE",
      "live.baseLabel": "网关地址",
      "live.test": "测试连接",
      "live.enable": "启用",
      "live.disable": "停用",
      "live.hint": "未启用时页面只回放 mock 账本，不会发起任何网络请求。",
      "live.testing": "正在测试连接…",
      "live.testOk": "连接成功，策略 {policy}，后端 {backends}",
      "live.testFail": "连接失败：{error}",
      "live.needBase": "请先填写网关地址。",
      "live.promptLabel": "测试任务",
      "live.run": "发送请求",
      "live.running": "正在请求网关…",
      "live.fallback": "在线请求失败，已保留离线回放：{error}",
      "live.resultTitle": "网关返回",
      "live.policy": "策略",
      "live.cost": "成本",
      "live.attempts": "尝试次数",
      "live.escalated": "是否升级",
      "live.confidence": "置信度",
      "live.latency": "总延迟",
      "live.response": "回答",

      "footer": "纯静态页面 · 默认回放确定性 mock 账本；在线模式需要你自托管的 OpenAI 兼容网关，连接失败会保留离线回放。"
    },

    en: {
      "app.title": "When to Escalate — When should you pay for the frontier model?",
      "app.desc": "A cascade-inference cost panel: the small model answers first and the frontier model is used only on failure or low confidence.",
      "brand.sub": "cascade inference demo · when to escalate",
      "badge.mock": "MOCK LEDGER",
      "badge.real": "REAL LEDGER",
      "badge.mockTitle": "Showing a deterministic mock ledger, not measured model output. See F2.5 for the real-backend eval.",
      "lang.switch": "Switch to Chinese",
      "lang.button": "中文",

      "hero.title": "When should a request go to the frontier model?",
      "hero.body": "Run the same task flow through three architectures: all-frontier, smart cascade, and all-small. The cascade answers with the small model first and escalates only on failure or low confidence, counting every attempt in <code>CPST</code> (Cost per Successful Task). Switch policies and move the sliders to watch unit economics change.",
      "hero.switchAria": "Policy switch",

      "policy.all_frontier": "All frontier",
      "policy.all_frontier.tag": "all_frontier",
      "policy.cascade": "Smart cascade",
      "policy.cascade.tag": "cascade · recommended",
      "policy.all_small": "All small",
      "policy.all_small.tag": "all_small",

      "banner.loadFail": "<b>Failed to load web/data/ledger.json:</b> {error}. Rebuild it with python3 cascade/src/replay.py.",

      "replay.title": "Per-task routing chain",
      "replay.sub": "Deterministic mock ledger · {total} tasks",
      "replay.count": "{shown} / {total} tasks",
      "filter.all": "All",
      "filter.escalated": "Escalated",
      "filter.failed": "Failed",
      "task.empty": "No tasks match this filter.",
      "task.confidence": "confidence {value}",
      "task.cost": "cost ${value}",
      "task.attempts": "{n} attempts",
      "task.escalated": "escalated",
      "task.success": "success",
      "task.failed": "failed",
      "task.startReason": "small model answers first",
      "task.escalateFail": "small model failed → escalate to frontier",
      "task.escalateConf": "confidence {c} is below threshold {t} → escalate to frontier",
      "task.kept": "confidence passed the threshold; keep the small answer",
      "task.frontierOnly": "policy: every task goes straight to the frontier model",
      "task.allSmallOnly": "policy: every task stays on the small model",
      "task.smallRetry": "small model failed → retry the small model",
      "task.chainSmall": "small",
      "task.chainFrontier": "frontier",

      "kind.simple": "Simple",
      "kind.medium": "Medium",
      "kind.complex": "Complex",
      "difficulty.low": "low difficulty",
      "difficulty.medium": "medium difficulty",
      "difficulty.high": "high difficulty",
      "model.small": "small model",
      "model.frontier": "frontier model",

      "metrics.title": "Live metrics",
      "metrics.sub": "Recomputed as policy and parameters change · mock",
      "metric.totalCost": "Total cost",
      "metric.cpst": "CPST",
      "metric.success": "Success rate",
      "metric.escalation": "Escalation rate",
      "metric.latency": "Avg latency",
      "metric.savings": "Savings vs all-frontier",
      "metric.failedCost": "Wasted on failures",

      "compare.title": "Three-policy comparison",
      "compare.sub": "Same task flow · same parameters · mock values",
      "compare.total": "Total cost",
      "compare.cpst": "CPST",
      "compare.success": "Success",
      "compare.active": "current policy",

      "params.title": "Adjustable parameters",
      "params.sub": "Threshold, prices and traffic mix recompute unit economics live",
      "params.reset": "Reset to defaults",
      "params.mockNote": "Example prices and mock traces are illustrative only, not a vendor quote.",
      "params.threshold": "Confidence threshold",
      "params.smallInput": "Small input price / 1M tokens",
      "params.smallOutput": "Small output price / 1M tokens",
      "params.frontierInput": "Frontier input price / 1M tokens",
      "params.frontierOutput": "Frontier output price / 1M tokens",
      "params.mix": "Traffic mix weights",
      "params.simple": "Simple tasks",
      "params.medium": "Medium tasks",
      "params.complex": "Complex tasks",

      "live.title": "Online mode (self-hosted gateway)",
      "live.sub": "Connect an OpenAI-compatible cascade gateway and validate routing with real requests",
      "live.badgeOn": "LIVE",
      "live.badgeOff": "OFFLINE",
      "live.baseLabel": "Gateway endpoint",
      "live.test": "Test connection",
      "live.enable": "Enable",
      "live.disable": "Disable",
      "live.hint": "While disabled the page only replays the mock ledger and makes no network requests.",
      "live.testing": "Testing connection…",
      "live.testOk": "Connected. Policy {policy}, backends {backends}",
      "live.testFail": "Connection failed: {error}",
      "live.needBase": "Enter the gateway endpoint first.",
      "live.promptLabel": "Test task",
      "live.run": "Send request",
      "live.running": "Requesting the gateway…",
      "live.fallback": "Online request failed; offline replay is still available: {error}",
      "live.resultTitle": "Gateway response",
      "live.policy": "Policy",
      "live.cost": "Cost",
      "live.attempts": "Attempts",
      "live.escalated": "Escalated",
      "live.confidence": "Confidence",
      "live.latency": "Total latency",
      "live.response": "Answer",

      "footer": "Static page · replays a deterministic mock ledger by default; online mode needs your self-hosted OpenAI-compatible gateway, and a failed connection keeps the offline replay."
    }
  };

  var STORAGE_KEY = "wte.lang";
  var listeners = [];
  var current = detect();

  function detect() {
    var param = null;
    try {
      param = new root.URLSearchParams(root.location.search).get("lang");
    } catch (e) {
      param = null;
    }
    if (param && DICT[param]) return param;
    try {
      var saved = root.localStorage.getItem(STORAGE_KEY);
      if (saved && DICT[saved]) return saved;
    } catch (e) {
      // localStorage can be unavailable in private mode; fall through.
    }
    return /^zh/i.test(root.navigator.language || "") ? "zh" : "en";
  }

  function t(key, vars) {
    var table = DICT[current] || DICT.zh;
    var text = table[key];
    if (text == null) text = DICT.zh[key];
    if (text == null) return key;
    if (!vars) return text;
    return text.replace(/\{(\w+)\}/g, function (match, name) {
      return vars[name] == null ? match : String(vars[name]);
    });
  }

  function label(prefix, value) {
    var key = prefix + "." + value;
    var text = t(key);
    return text === key ? value : text;
  }

  function getLang() {
    return current;
  }

  function applyDom(rootNode) {
    var scope = rootNode || document;
    scope.querySelectorAll("[data-i18n]").forEach(function (node) {
      node.textContent = t(node.getAttribute("data-i18n"));
    });
    scope.querySelectorAll("[data-i18n-html]").forEach(function (node) {
      node.innerHTML = t(node.getAttribute("data-i18n-html"));
    });
    scope.querySelectorAll("[data-i18n-title]").forEach(function (node) {
      node.setAttribute("title", t(node.getAttribute("data-i18n-title")));
    });
    document.documentElement.lang = current === "zh" ? "zh-CN" : "en";
    document.title = t("app.title");
    var meta = document.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute("content", t("app.desc"));
  }

  function setLang(lang) {
    if (!DICT[lang] || lang === current) return;
    current = lang;
    try {
      root.localStorage.setItem(STORAGE_KEY, lang);
    } catch (e) {
      // Persisting is best-effort only.
    }
    applyDom();
    listeners.forEach(function (fn) { fn(current); });
  }

  function onChange(fn) {
    listeners.push(fn);
  }

  root.WTEI18n = {
    t: t,
    label: label,
    getLang: getLang,
    setLang: setLang,
    onChange: onChange,
    applyDom: applyDom
  };
})(typeof window !== "undefined" ? window : this);
