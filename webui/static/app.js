(() => {
  const THEMES = window.ACL_THEMES || [];
  const CONFIG_OPTIONS = window.ACL_CONFIG_OPTIONS || { asa: [], fortigate: [] };
  const HISTORY_ENABLED = window.ACL_HISTORY_ENABLED !== false;
  const SEARCH_LIMIT = window.ACL_SEARCH_LIMIT || 50;

  const PREF_COOKIE = "acl_theme_pref";
  const THEME_KEY = "acl_theme";
  const HL_KEY = "acl_highlight";
  const HIST_VIS_KEY = "acl_history_visible";

  let activeTab = "rules";
  let stateGuard = false;
  let themePref = {};

  function storageGet(key, fallback) {
    try {
      if (typeof window !== "undefined" && "localStorage" in window) {
        const value = window.localStorage.getItem(key);
        return value === null || value === undefined ? fallback : value;
      }
    } catch (err) {
      console.warn("storageGet failed", err);
    }
    return fallback;
  }

  function storageSet(key, value) {
    try {
      if (typeof window !== "undefined" && "localStorage" in window) {
        window.localStorage.setItem(key, value);
      }
    } catch (err) {
      console.warn("storageSet failed", err);
    }
  }

  function cookieGet(name) {
    if (typeof document === "undefined") {
      return null;
    }
    const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : null;
  }

  function cookieSet(name, value) {
    if (typeof document === "undefined") {
      return;
    }
    const ttl = 60 * 60 * 24 * 365;
    document.cookie = `${name}=${encodeURIComponent(value)};path=/;max-age=${ttl}`;
  }

  function loadThemePrefs() {
    try {
      return JSON.parse(cookieGet(PREF_COOKIE) || "{}") || {};
    } catch (err) {
      return {};
    }
  }

  function saveThemePrefs() {
    try {
      cookieSet(PREF_COOKIE, JSON.stringify(themePref));
    } catch (err) {
      console.warn("saveThemePrefs failed", err);
    }
  }

  function themeByName(name, kind) {
    return THEMES.find((t) => t.name === name && (!kind || t.kind === kind));
  }

  function ensureThemePref() {
    ["dark", "light"].forEach((kind) => {
      const available = THEMES.filter((t) => t.kind === kind);
      if (!available.length) {
        return;
      }
      const current = themePref[kind];
      if (!current || !themeByName(current, kind)) {
        themePref[kind] = available[0].name;
      }
    });
  }

  function themeForKind(kind) {
    ensureThemePref();
    return themeByName(themePref[kind], kind) || THEMES.find((t) => t.kind === kind) || THEMES[0];
  }

  function applyThemeVars(theme) {
    if (!theme || !theme.vars) {
      return;
    }
    const root = document.documentElement;
    for (const [key, val] of Object.entries(theme.vars)) {
      root.style.setProperty(`--${key}`, val);
    }
  }

  function updateThemePreview(kind) {
    const target = document.getElementById(kind === "light" ? "preview_light" : "preview_dark");
    if (!target) {
      return;
    }
    const theme = themeForKind(kind);
    if (!theme) {
      return;
    }
    target.style.background = theme.vars.bg;
    target.style.color = theme.vars.text;
    target.style.borderColor = theme.vars.border;
    target.textContent = theme.name;
  }

  function populateThemeSelect(kind) {
    const select = document.getElementById(kind === "light" ? "theme_light" : "theme_dark");
    if (!select) {
      return;
    }
    const themes = THEMES.filter((t) => t.kind === kind);
    select.innerHTML = "";
    themes.forEach((theme) => {
      const opt = document.createElement("option");
      opt.value = theme.name;
      opt.textContent = theme.name;
      select.appendChild(opt);
    });
    ensureThemePref();
    if (themePref[kind] && themeByName(themePref[kind], kind)) {
      select.value = themePref[kind];
    }
    select.onchange = (event) => {
      themePref[kind] = event.target.value;
      ensureThemePref();
      saveThemePrefs();
      applyTheme();
      updateThemePreview(kind);
    };
    updateThemePreview(kind);
  }

  function populateThemeSelectors() {
    populateThemeSelect("dark");
    populateThemeSelect("light");
  }

  function applyTheme() {
    const mode = storageGet(THEME_KEY, "dark");
    const root = document.documentElement;
    root.dataset.theme = mode;
    const theme = themeForKind(mode === "light" ? "light" : "dark");
    applyThemeVars(theme);
    themePref[mode] = theme ? theme.name : themePref[mode];
    const toggle = document.getElementById("themeToggle");
    if (toggle) {
      toggle.checked = mode === "light";
    }
    updateThemePreview("dark");
    updateThemePreview("light");
  }

  function toggleTheme() {
    const current = storageGet(THEME_KEY, "dark");
    const next = current === "dark" ? "light" : "dark";
    storageSet(THEME_KEY, next);
    applyTheme();
  }

  function highlightAll(enable) {
    document.body.classList.toggle("hl-off", !enable);
    storageSet(HL_KEY, enable ? "on" : "off");
  }

  function toggleHighlight() {
    const checked = document.getElementById("hlToggle")?.checked;
    highlightAll(!!checked);
  }

  function populateConfigs() {
    const asaSelect = document.getElementById("config");
    const ftgSelect = document.getElementById("config_ftg");
    if (asaSelect) {
      asaSelect.innerHTML = CONFIG_OPTIONS.asa
        .map((name) => `<option value='${name}'>${name}</option>`)
        .join("");
    }
    if (ftgSelect) {
      ftgSelect.innerHTML = CONFIG_OPTIONS.fortigate
        .map((name) => `<option value='${name}'>${name}</option>`)
        .join("");
    }
  }

  function toggleVendor() {
    const vendor = document.getElementById("vendor").value;
    const asa = document.getElementById("asa_cfg");
    const ftg = document.getElementById("ftg_cfg");
    if (asa) {
      asa.style.display = vendor === "asa" ? "block" : "none";
    }
    if (ftg) {
      ftg.style.display = vendor === "fortigate" ? "block" : "none";
    }
  }

  function listHistory() {
    const panel = document.getElementById("history");
    if (!panel || !HISTORY_ENABLED) {
      return;
    }
    fetch("/api/history")
      .then((resp) => (resp.ok ? resp.json() : Promise.reject()))
      .then((data) => {
        const items = data.entries || [];
        panel.innerHTML = items
          .map(
            (entry) =>
              `<button class="hist-entry" data-mode="${entry.tab}" data-query="${entry.query}"><span class="hist-desc">${entry.query}</span> <span class="hist-time">${new Date(
                entry.timestamp * 1000
              ).toLocaleString()}</span></button>`
          )
          .join("");
        panel.dataset.hasEntries = items.length ? "1" : "0";
        if (storageGet(HIST_VIS_KEY, "off") === "on") {
          panel.style.display = items.length ? "block" : "none";
        }
      })
      .catch(() => {});
  }

  function toggleHistory() {
    const panel = document.getElementById("history");
    if (!panel) {
      return;
    }
    const visible = panel.style.display !== "none";
    panel.style.display = visible ? "none" : "block";
    storageSet(HIST_VIS_KEY, visible ? "off" : "on");
    if (!visible) {
      listHistory();
    }
  }

  function setMode(mode) {
    const modeInput = document.getElementById("mode");
    if (modeInput) {
      modeInput.value = mode;
    }
    const fuzzy = document.getElementById("fuzzy");
    if (fuzzy) {
      fuzzy.checked = mode === "rules";
    }
    const runActions = document.getElementById("run_actions");
    if (runActions) {
      runActions.style.display = ["rules", "find", "packet"].includes(mode) ? "block" : "none";
    }
    if (mode === "inspect" || mode === "compare") {
      const radio = document.querySelector(`input[name='rule_mode'][value='${mode}']`);
      if (radio && !radio.checked) {
        radio.checked = true;
      }
    }
    updateRuleModeUI(mode);
  }

  function updateRuleModeUI(mode) {
    const inspect = document.getElementById("inspect_fields");
    const compare = document.getElementById("compare_fields");
    if (inspect) {
      inspect.style.display = mode === "inspect" ? "block" : "none";
    }
    if (compare) {
      compare.style.display = mode === "compare" ? "block" : "none";
    }
  }

  function activateTab(tab, suppressSave) {
    activeTab = tab;
    const panels = document.querySelectorAll(".tab-panel");
    panels.forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${tab}`));
    const buttons = document.querySelectorAll(".mode-tabs .tab");
    buttons.forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === tab));
    const service = document.getElementById("service_filters");
    const includeAnyLabel = document.getElementById("include_any_label");
    const cfgSection = document.querySelector(".section-config");
    if (cfgSection) {
      cfgSection.style.display = tab === "rules" || tab === "packet" ? "block" : "none";
    }
    const searchRow = document.querySelector(".global-search");
    if (searchRow) {
      searchRow.style.display = tab === "rules" ? "block" : "none";
    }
    document.querySelectorAll(".results[data-tab]").forEach((panel) => {
      panel.style.display = panel.dataset.tab === tab ? "block" : "none";
    });
    const runActions = document.getElementById("run_actions");
    if (runActions) {
      runActions.style.display = ["rules", "find", "packet"].includes(tab) ? "block" : "none";
    }
    if (tab === "rules") {
      const selected = document.querySelector("input[name='rule_mode']:checked");
      const chosen = selected ? selected.value : "inspect";
      setMode(chosen);
      if (service) {
        service.style.display = "block";
      }
      if (includeAnyLabel) {
        includeAnyLabel.style.display = "inline-flex";
      }
    } else if (tab === "find") {
      setMode("find");
      if (service) {
        service.style.display = "none";
      }
      if (includeAnyLabel) {
        includeAnyLabel.style.display = "none";
      }
    } else if (tab === "packet") {
      setMode("packet");
      if (service) {
        service.style.display = "block";
      }
      if (includeAnyLabel) {
        includeAnyLabel.style.display = "none";
      }
    } else {
      if (service) {
        service.style.display = "none";
      }
      if (includeAnyLabel) {
        includeAnyLabel.style.display = "none";
      }
    }
    if (tab === "config") {
      loadConfigText("current");
    }
    if (!suppressSave) {
      saveState();
    }
    setTimeout(() => highlightAll((storageGet(HL_KEY, "on") || "on") === "on"), 0);
  }

  function debounce(fn, ms) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  function currentConfig() {
    const vendor = document.getElementById("vendor").value;
    const config = vendor === "asa"
      ? document.getElementById("config").value
      : document.getElementById("config_ftg").value;
    return { vendor, config };
  }

  function fillDatalist(items) {
    const dl = document.getElementById("targets");
    if (!dl) {
      return;
    }
    dl.innerHTML = "";
    for (const entry of items) {
      const opt = document.createElement("option");
      opt.value = entry.value;
      opt.label = entry.label || entry.value;
      dl.appendChild(opt);
    }
  }

  const fetchSuggest = debounce(async function (event) {
    if (activeTab !== "rules") {
      fillDatalist([]);
      return;
    }
    const q = event.target.value;
    if (!q || q.length < 1) {
      fillDatalist([]);
      return;
    }
    const { vendor, config } = currentConfig();
    const mode = document.getElementById("fuzzy").checked ? "fuzzy" : "prefix";
    try {
      const resp = await fetch(
        `/api/objects?vendor=${vendor}&os=${vendor.toUpperCase()}&version=auto&config=${encodeURIComponent(
          config
        )}&q=${encodeURIComponent(q)}&mode=${mode}&limit=${SEARCH_LIMIT}`
      );
      if (!resp.ok) {
        return;
      }
      const data = await resp.json();
      fillDatalist(data.items || []);
    } catch (err) {
      console.warn("fetchSuggest failed", err);
    }
  },
  150);

  function attachTypeahead() {
    ["inspect", "old", "new", "pkt_src", "pkt_dst", "findq"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("input", fetchSuggest);
      }
    });
  }

  function saveState() {
    if (stateGuard) {
      return;
    }
    const payload = {
      tab: activeTab,
      vendor: document.getElementById("vendor").value,
      config: document.getElementById("config").value,
      config_ftg: document.getElementById("config_ftg").value,
      mode: document.getElementById("mode").value,
      inspect: document.getElementById("inspect").value,
      old: document.getElementById("old").value,
      new: document.getElementById("new").value,
      findq: document.getElementById("findq").value,
      pkt_src: document.getElementById("pkt_src").value,
      pkt_dst: document.getElementById("pkt_dst").value,
      proto: document.querySelector("select[name='proto']").value,
      dport: document.querySelector("input[name='dport']").value,
      include_any: document.getElementById("include_any").checked,
    };
    storageSet("acl_state", JSON.stringify(payload));
  }

  function loadState() {
    let payload = null;
    try {
      payload = JSON.parse(storageGet("acl_state", "{}"));
    } catch (err) {
      payload = null;
    }
    if (!payload) {
      return;
    }
    stateGuard = true;
    try {
      const vendor = document.getElementById("vendor");
      if (vendor && payload.vendor) {
        vendor.value = payload.vendor;
      }
      toggleVendor();
      const assign = (id, value) => {
        const elem = document.getElementById(id);
        if (elem && value !== undefined) {
          elem.value = value;
        }
      };
      assign("config", payload.config);
      assign("config_ftg", payload.config_ftg);
      assign("inspect", payload.inspect);
      assign("old", payload.old);
      assign("new", payload.new);
      assign("findq", payload.findq);
      assign("pkt_src", payload.pkt_src);
      assign("pkt_dst", payload.pkt_dst);
      const protoSelect = document.querySelector("select[name='proto']");
      if (protoSelect && payload.proto !== undefined) {
        protoSelect.value = payload.proto;
      }
      const dportInput = document.querySelector("input[name='dport']");
      if (dportInput && payload.dport !== undefined) {
        dportInput.value = payload.dport;
      }
      const includeAny = document.getElementById("include_any");
      if (includeAny && payload.include_any !== undefined) {
        includeAny.checked = payload.include_any;
      }
      if (payload.tab) {
        activateTab(payload.tab, true);
      }
      if (payload.mode) {
        setMode(payload.mode);
      }
    } finally {
      stateGuard = false;
    }
  }

  function loadConfigText(which) {
    const textarea = document.getElementById("config_text");
    if (!textarea) {
      return;
    }
    const { vendor, config } = currentConfig();
    if (!config) {
      textarea.value = "";
      return;
    }
    fetch(`/api/config?vendor=${vendor}&config=${encodeURIComponent(config)}`)
      .then((resp) => (resp.ok ? resp.json() : Promise.reject()))
      .then((data) => {
        textarea.value = data.text || "";
      })
      .catch(() => {
        textarea.value = "";
      });
  }

  function setRunResults(tab, htmlContent) {
    const targetTab = tab || "rules";
    const container = document.querySelector(`.results[data-tab='${targetTab}']`);
    if (container) {
      container.innerHTML = htmlContent || "";
      container.dataset.tabActive = "1";
    }
    if (targetTab !== activeTab) {
      activateTab(targetTab);
    }
  }

  async function submitForm(event) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);
    const params = new URLSearchParams();
    formData.forEach((value, key) => {
      params.append(key, value);
    });
    try {
      const resp = await fetch("/run", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: params.toString(),
      });
      const data = await resp.json();
      if (!resp.ok || data.error) {
        setRunResults("rules", `<div class="section"><p style="color:red">${(data && data.error) || "Failed to run"}</p></div>`);
        return;
      }
      setRunResults(data.tab || "rules", data.html || "");
      saveState();
      listHistory();
    } catch (err) {
      setRunResults("rules", `<div class="section"><p style="color:red">Request failed: ${err}</p></div>`);
    }
  }

  function refreshMeta() {
    const { vendor, config } = currentConfig();
    const metaSpan = document.getElementById("meta");
    if (!config || !metaSpan) {
      return;
    }
    fetch(`/api/meta?vendor=${vendor}&config=${encodeURIComponent(config)}`)
      .then((resp) => (resp.ok ? resp.json() : Promise.reject()))
      .then((data) => {
        metaSpan.textContent = data.version ? `${data.os} ${data.version}` : data.os || vendor.toUpperCase();
      })
      .catch(() => {
        metaSpan.textContent = "";
      });
  }

  function ensureHistoryVisibility() {
    if (!HISTORY_ENABLED) {
      return;
    }
    const vis = storageGet(HIST_VIS_KEY, "off") === "on";
    const panel = document.getElementById("history");
    if (panel) {
      panel.style.display = vis ? "block" : "none";
    }
    if (vis) {
      listHistory();
    }
  }

  function init() {
    themePref = loadThemePrefs();
    populateConfigs();
    toggleVendor();
    populateThemeSelectors();
    applyTheme();
    highlightAll((storageGet(HL_KEY, "on") || "on") === "on");
    attachTypeahead();
    loadState();
    refreshMeta();
    ensureHistoryVisibility();

    const themeToggle = document.getElementById("themeToggle");
    if (themeToggle) {
      themeToggle.addEventListener("change", toggleTheme);
    }
    const hlToggle = document.getElementById("hlToggle");
    if (hlToggle) {
      hlToggle.checked = (storageGet(HL_KEY, "on") || "on") === "on";
      hlToggle.addEventListener("change", toggleHighlight);
    }
    const histToggle = document.getElementById("histToggle");
    if (histToggle) {
      histToggle.addEventListener("click", toggleHistory);
      histToggle.style.display = HISTORY_ENABLED ? "inline-flex" : "none";
    }
    document.getElementById("vendor").addEventListener("change", () => {
      toggleVendor();
      refreshMeta();
      saveState();
    });
    document.querySelectorAll("input[name='rule_mode']").forEach((radio) => {
      radio.addEventListener("change", (event) => {
        setMode(event.target.value);
        saveState();
      });
    });
    document.querySelectorAll(".mode-tabs .tab").forEach((tab) => {
      tab.addEventListener("click", () => activateTab(tab.dataset.tab));
    });
    document.forms[0].addEventListener("change", saveState);
    document.forms[0].addEventListener("input", saveState);
    document.forms[0].addEventListener("submit", submitForm);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
*** End Patch
