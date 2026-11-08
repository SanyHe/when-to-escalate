// Remote gateway client for the When-to-Escalate demo.
//
// The page normally replays the deterministic mock ledger. This module adds an
// optional live channel: when enabled, it sends a test prompt to a self-hosted,
// OpenAI-compatible cascade gateway (see cascade/src/gateway.py) and renders the
// real routing chain and cost metadata.
//
// Exposes window.WTEMote:
//   getConfig() / saveConfig(cfg)   read/persist settings (localStorage)
//   isEnabled()                     true when an endpoint is configured
//   ping()                          -> {ok, policy, backends}
//   complete(prompt)                -> gateway response body
//   normalizeUrl(baseUrl)           accept host:port shorthand
//
// Nothing is sent anywhere until the visitor explicitly enables live mode, so
// the default static replay stays fully offline. The gateway address is stored
// locally only; no API key is kept in the page.

(function (root) {
  "use strict";

  var STORAGE_KEY = "wte.remote";

  function defaults() {
    return { baseUrl: "", enabled: false };
  }

  function getConfig() {
    var cfg = defaults();
    try {
      var raw = root.localStorage.getItem(STORAGE_KEY);
      if (!raw) return cfg;
      var parsed = JSON.parse(raw);
      if (typeof parsed.baseUrl === "string") cfg.baseUrl = parsed.baseUrl;
      cfg.enabled = !!parsed.enabled;
    } catch (err) {
      return defaults();
    }
    return cfg;
  }

  function saveConfig(cfg) {
    try {
      root.localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg));
    } catch (err) {
      // Persisting is best-effort only.
    }
  }

  function isEnabled() {
    var cfg = getConfig();
    return cfg.enabled && !!cfg.baseUrl;
  }

  function normalizeUrl(baseUrl) {
    var url = String(baseUrl || "").trim().replace(/\/+$/, "");
    if (!url) return "";
    if (!/^https?:\/\//i.test(url)) url = "https://" + url;
    return url;
  }

  function errorText(status, body) {
    var detail = body;
    try {
      var parsed = JSON.parse(body);
      if (parsed && parsed.error && parsed.error.message) {
        detail = parsed.error.message;
      }
    } catch (err) { /* plain text body */ }
    return "HTTP " + status + (detail ? ": " + String(detail).slice(0, 160) : "");
  }

  function ping() {
    var cfg = getConfig();
    var base = normalizeUrl(cfg.baseUrl);
    if (!base) return Promise.reject(new Error("endpoint is empty"));
    return fetch(base + "/healthz", { method: "GET" })
      .then(function (response) {
        return response.text().then(function (body) {
          if (!response.ok) throw new Error(errorText(response.status, body));
          var parsed = {};
          try { parsed = JSON.parse(body); } catch (err) { /* tolerate empty */ }
          return {
            ok: true,
            policy: parsed.policy || "cascade",
            backends: (parsed.backends || []).join(", ") || "—",
          };
        });
      });
  }

  function complete(prompt) {
    var cfg = getConfig();
    var base = normalizeUrl(cfg.baseUrl);
    if (!base) return Promise.reject(new Error("endpoint is empty"));
    var payload = {
      model: "cascade",
      messages: [{ role: "user", content: String(prompt || "") }],
      temperature: 0,
      stream: false,
    };
    return fetch(base + "/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function (response) {
      return response.text().then(function (body) {
        if (!response.ok) throw new Error(errorText(response.status, body));
        var parsed = JSON.parse(body);
        var choice = (parsed.choices || [])[0] || {};
        var message = choice.message || {};
        return {
          content: String(message.content || ""),
          cascade: parsed.cascade || null,
          usage: parsed.usage || null,
        };
      });
    });
  }

  root.WTEMote = {
    getConfig: getConfig,
    saveConfig: saveConfig,
    isEnabled: isEnabled,
    normalizeUrl: normalizeUrl,
    ping: ping,
    complete: complete,
  };
})(window);
