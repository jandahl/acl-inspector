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

  function parseBool(value, fallback = false) {
    if (value === null || value === undefined || value === "") {
      return fallback;
    }
    const text = String(value).toLowerCase();
    if (["1", "true", "yes", "on"].includes(text)) {
      return true;
    }
    if (["0", "false", "no", "off"].includes(text)) {
      return false;
    }
    return fallback;
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
    const body = document.body;
    if (body) {
      body.classList.remove("theme-dark", "theme-light");
      body.classList.add(mode === "light" ? "theme-light" : "theme-dark");
    }
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

  function escapeHtml(text) {
    return (text || "").replace(/[&<>"']/g, (ch) => {
      switch (ch) {
        case "&":
          return "&amp;";
        case "<":
          return "&lt;";
        case ">":
          return "&gt;";
        case '"':
          return "&quot;";
        case "'":
          return "&#39;";
        default:
          return ch;
      }
    });
  }

  function highlightAsaBlock(text) {
    let html = escapeHtml(text);
    html = html.replace(/\b(permit|deny)\b/gi, "<span class='act'>$1</span>");
    html = html.replace(/\b(tcp|udp|icmp|ip)\b/gi, "<span class='proto'>$1</span>");
    html = html.replace(
      /\b(access-list|extended|object-group|object|host|subnet|eq|lt|gt|neq|range|any|any4|any6)\b/gi,
      "<span class='kw'>$1</span>"
    );
    html = html.replace(
      /\b(\d{1,3}(?:\.\d{1,3}){3})(?:\/(\d{1,2}))?\b/g,
      (_match, addr, mask) => `<span class='addr'>${addr}${mask ? `/${mask}` : ""}</span>`
    );
    html = html.replace(/\b(\d{2,5})\b/g, "<span class='num'>$1</span>");
    return html;
  }

  function applyHighlight(pre, enable) {
    if (!pre.dataset.raw) {
      pre.dataset.raw = pre.textContent || "";
    }
    const raw = pre.dataset.raw || "";
    if (!enable) {
      pre.textContent = raw;
      return;
    }
    const lang = (pre.dataset.lang || "").toLowerCase();
    if (lang === "asa") {
      pre.innerHTML = highlightAsaBlock(raw);
      return;
    }
    pre.textContent = raw;
  }

  function refreshHighlights(enable) {
    document.querySelectorAll("pre[data-lang]").forEach((pre) => {
      applyHighlight(pre, enable);
    });
  }

  function highlightAll(enable) {
    if (document.body) {
      document.body.classList.toggle("hl-off", !enable);
    }
    refreshHighlights(enable);
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
        attachHistoryHandlers();
        if (storageGet(HIST_VIS_KEY, "off") === "on") {
          panel.style.display = items.length ? "block" : "none";
        }
      })
      .catch(() => {});
  }

  function attachHistoryHandlers() {
    const panel = document.getElementById("history");
    if (!panel) {
      return;
    }
    panel.querySelectorAll(".hist-entry").forEach((button) => {
      button.addEventListener("click", () => {
        const tab = button.dataset.mode || "rules";
        const query = button.dataset.query || "";
        restoreFromHistory(tab, query);
      });
    });
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

  function updateRunActions(tab) {
    document.querySelectorAll(".actions-run").forEach((node) => {
      const shouldShow = node.dataset.tab === tab && ["rules", "find", "packet"].includes(tab);
      node.style.display = shouldShow ? "block" : "none";
    });
  }

  function restoreFromHistory(tab, query) {
    if (!tab) {
      return;
    }
    const normalizedTab = tab || "rules";
    const cleanQuery = query || "";
    stateGuard = true;
    try {
      if (normalizedTab === "rules") {
        const isCompare = cleanQuery.includes("->");
        activateTab("rules", true);
        setMode(isCompare ? "compare" : "inspect");
        const inspectField = document.getElementById("inspect");
        const oldField = document.getElementById("old");
        const newField = document.getElementById("new");
        if (inspectField) {
          inspectField.value = isCompare ? "" : cleanQuery;
        }
        const parts = cleanQuery.split("->");
        if (oldField) {
          oldField.value = isCompare ? (parts[0] || "") : "";
        }
        if (newField) {
          newField.value = isCompare ? (parts[1] || "") : "";
        }
      } else if (normalizedTab === "find") {
        activateTab("find", true);
        setMode("find");
        const findField = document.getElementById("findq");
        if (findField) {
          findField.value = cleanQuery;
        }
      } else if (normalizedTab === "packet") {
        activateTab("packet", true);
        setMode("packet");
        const [srcVal = "", dstVal = ""] = cleanQuery.split("->");
        const srcField = document.getElementById("pkt_src");
        const dstField = document.getElementById("pkt_dst");
        if (srcField) {
          srcField.value = srcVal;
        }
        if (dstField) {
          dstField.value = dstVal;
        }
      } else {
        activateTab(normalizedTab, true);
      }
    } finally {
      stateGuard = false;
    }
    saveState();
    triggerRun();
  }

  function setMode(mode) {
    const modeInput = document.getElementById("mode");
    if (modeInput) {
      modeInput.value = mode;
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
      const isActive = panel.dataset.tab === tab;
      panel.style.display = isActive ? "block" : "none";
      panel.classList.toggle("active", isActive);
    });
    updateRunActions(tab);
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
      loadConfigText();
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

  function gatherState() {
    const vendor = document.getElementById("vendor").value;
    return {
      tab: activeTab,
      vendor,
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
      fuzzy: document.getElementById("fuzzy").checked,
    };
  }

  function updateUrlFromState(state) {
    if (typeof window === "undefined" || !window.history || !window.location) {
      return;
    }
    const params = new URLSearchParams();
    const assign = (key, value) => {
      if (value === null || value === undefined) {
        return;
      }
      const text = typeof value === "string" ? value.trim() : String(value);
      if (text) {
        params.set(key, text);
      }
    };
    assign("tab", state.tab);
    assign("mode", state.mode);
    assign("vendor", state.vendor);
    assign("config", state.config);
    assign("config_ftg", state.config_ftg);
    assign("inspect", state.inspect);
    assign("old", state.old);
    assign("new", state.new);
    assign("find", state.findq);
    assign("pkt_src", state.pkt_src);
    assign("pkt_dst", state.pkt_dst);
    assign("proto", state.proto);
    assign("dport", state.dport);
    if (state.include_any) {
      params.set("include_any", "1");
    }
    params.set("fuzzy", state.fuzzy ? "1" : "0");
    const query = params.toString();
    const url = query ? `${window.location.pathname}?${query}` : window.location.pathname;
    try {
      window.history.replaceState({}, "", url);
    } catch (err) {
      console.warn("replaceState failed", err);
    }
  }

  function parseQueryState() {
    if (typeof window === "undefined") {
      return null;
    }
    const params = new URLSearchParams(window.location.search || "");
    if (!Array.from(params.keys()).length) {
      return null;
    }
    const state = {};
    let hasValue = false;
    const take = (key, target) => {
      const value = params.get(key);
      if (value !== null) {
        state[target] = value;
        hasValue = true;
      }
    };
    take("tab", "tab");
    take("mode", "mode");
    take("vendor", "vendor");
    take("config", "config");
    take("config_ftg", "config_ftg");
    take("inspect", "inspect");
    take("old", "old");
    take("new", "new");
    take("find", "findq");
    take("findq", "findq");
    take("pkt_src", "pkt_src");
    take("pkt_dst", "pkt_dst");
    take("proto", "proto");
    take("dport", "dport");
    if (params.has("include_any")) {
      state.include_any = parseBool(params.get("include_any"), false);
      hasValue = true;
    }
    if (params.has("fuzzy")) {
      state.fuzzy = parseBool(params.get("fuzzy"), true);
      hasValue = true;
    }
    return hasValue ? state : null;
  }

  function applyState(payload) {
    if (!payload) {
      return false;
    }
    stateGuard = true;
    try {
      if (payload.vendor) {
        const vendorSelect = document.getElementById("vendor");
        if (vendorSelect) {
          vendorSelect.value = payload.vendor;
        }
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
        includeAny.checked = !!payload.include_any;
      }
      const fuzzyToggle = document.getElementById("fuzzy");
      if (fuzzyToggle && payload.fuzzy !== undefined) {
        fuzzyToggle.checked = !!payload.fuzzy;
      }
      const configSelectTab = document.getElementById("config_select_tab");
      const currentVendor = (document.getElementById("vendor")?.value || payload.vendor || "asa").toLowerCase();
      if (configSelectTab && currentVendor === "asa" && payload.config !== undefined) {
        configSelectTab.value = payload.config;
      }
    } finally {
      stateGuard = false;
    }
    if (payload.tab) {
      activateTab(payload.tab, true);
    }
    if (payload.mode) {
      setMode(payload.mode);
    }
    return true;
  }

  function shouldAutoRun(state) {
    if (!state || !state.tab) {
      return false;
    }
    if (state.tab === "rules") {
      if (state.mode === "compare") {
        return Boolean((state.old || "").trim() && (state.new || "").trim());
      }
      return Boolean((state.inspect || "").trim());
    }
    if (state.tab === "find") {
      return Boolean((state.findq || "").trim());
    }
    if (state.tab === "packet") {
      return Boolean((state.pkt_src || "").trim() && (state.pkt_dst || "").trim());
    }
    return false;
  }

  function saveState() {
    if (stateGuard) {
      return;
    }
    const payload = gatherState();
    storageSet("acl_state", JSON.stringify(payload));
    updateUrlFromState(payload);
  }

  function loadState() {
    const queryState = parseQueryState();
    if (queryState && applyState(queryState)) {
      return queryState;
    }
    let payload = null;
    try {
      payload = JSON.parse(storageGet("acl_state", "{}"));
    } catch (err) {
      payload = null;
    }
    if (payload && Object.keys(payload).length) {
      applyState(payload);
    }
    return null;
  }

  let currentConfigText = "";

  function updateConfigViewer(filterText) {
    const viewer = document.getElementById("config_text");
    if (!viewer) {
      return;
    }
    const filter = (filterText || "").trim().toLowerCase();
    if (!filter) {
      viewer.textContent = currentConfigText;
    } else {
      const lines = currentConfigText.split("\n").filter((line) => line.toLowerCase().includes(filter));
      viewer.textContent = lines.join("\n");
    }
    viewer.dataset.raw = viewer.textContent || "";
    const nameDisplay = document.getElementById("config_name_display");
    if (nameDisplay) {
      const { config } = currentConfig();
      nameDisplay.textContent = config || "n/a";
    }
    const hlToggle = document.getElementById("hlToggle");
    const highlightEnabled = hlToggle ? hlToggle.checked : (storageGet(HL_KEY, "on") || "on") === "on";
    refreshHighlights(highlightEnabled);
  }

  function loadConfigText() {
    const { vendor, config } = currentConfig();
    const viewer = document.getElementById("config_text");
    if (!viewer) {
      return;
    }
    if (!config) {
      currentConfigText = "";
      updateConfigViewer(document.getElementById("config_filter")?.value || "");
      return;
    }
    fetch(`/api/config?vendor=${vendor}&config=${encodeURIComponent(config)}`)
      .then((resp) => (resp.ok ? resp.json() : Promise.reject()))
      .then((data) => {
        currentConfigText = (data.text || "").replace(/\r\n?/g, "\n");
        updateConfigViewer(document.getElementById("config_filter")?.value || "");
      })
      .catch(() => {
        currentConfigText = "";
        updateConfigViewer("");
      });
  }

  function setRunResults(tab, htmlContent, meta) {
    let targetTab = tab || "rules";
    let container = document.querySelector(`.results[data-tab='${targetTab}']`);
    if (!container && targetTab !== "rules") {
      targetTab = "rules";
      container = document.querySelector(".results[data-tab='rules']");
    }
    if (container) {
      container.innerHTML = htmlContent || "";
    }
    activateTab(targetTab, true);
    const highlightToggle = document.getElementById("hlToggle");
    const enable = highlightToggle ? highlightToggle.checked : true;
    highlightAll(enable);
    if (meta) {
      if (meta.mode) {
        const modeInput = document.getElementById("mode");
        if (modeInput) {
          modeInput.value = meta.mode;
        }
        const radio = document.querySelector(`input[name='rule_mode'][value='${meta.mode}']`);
        if (radio) {
          radio.checked = true;
        }
        updateRuleModeUI(meta.mode);
      }
      if (meta.mode === "inspect" && typeof meta.query === "string") {
        const inspectField = document.getElementById("inspect");
        if (inspectField && !inspectField.value) {
          inspectField.value = meta.query;
        }
      }
      if (meta.mode === "compare" && typeof meta.query === "string") {
        const parts = meta.query.split("->");
        const oldField = document.getElementById("old");
        const newField = document.getElementById("new");
        if (oldField && !oldField.value && parts[0]) {
          oldField.value = parts[0];
        }
        if (newField && !newField.value && parts[1]) {
          newField.value = parts[1];
        }
      }
      if (meta.mode === "find" && typeof meta.query === "string") {
        const findField = document.getElementById("findq");
        if (findField && !findField.value) {
          findField.value = meta.query;
        }
      }
      if (meta.mode === "packet" && typeof meta.query === "string") {
        const [srcVal = "", dstVal = ""] = meta.query.split("->");
        const srcField = document.getElementById("pkt_src");
        const dstField = document.getElementById("pkt_dst");
        if (srcField && !srcField.value) {
          srcField.value = srcVal;
        }
        if (dstField && !dstField.value) {
          dstField.value = dstVal;
        }
      }
    }
  }

  async function submitForm(event) {
    if (event && typeof event.preventDefault === "function") {
      event.preventDefault();
    }
    const form = (event && event.target) ? event.target : document.forms[0];
    if (!form) {
      return;
    }
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
      setRunResults(data.tab || "rules", data.html || "", data.meta || null);
      saveState();
      listHistory();
    } catch (err) {
      setRunResults("rules", `<div class="section"><p style="color:red">Request failed: ${err}</p></div>`);
    }
  }

  function triggerRun() {
    const form = document.forms[0];
    if (!form) {
      return;
    }
    submitForm({ target: form });
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
    const configSelectTab = document.getElementById("config_select_tab");
    if (configSelectTab) {
      configSelectTab.innerHTML = CONFIG_OPTIONS.asa
        .map((name) => `<option value='${name}'>${name}</option>`)
        .join("");
      configSelectTab.addEventListener("change", () => {
        const vendorSelect = document.getElementById("vendor");
        if (vendorSelect && vendorSelect.value !== "asa") {
          vendorSelect.value = "asa";
          toggleVendor();
        }
        const option = configSelectTab.value;
        const mainSelect = document.getElementById("config");
        if (mainSelect && mainSelect.value !== option) {
          mainSelect.value = option;
        }
        loadConfigText();
      });
    }
    const configFilter = document.getElementById("config_filter");
    if (configFilter) {
      const updateConfig = () => updateConfigViewer(configFilter.value);
      const debouncedUpdateConfig = debounce(updateConfig, 120);
      configFilter.addEventListener("input", debouncedUpdateConfig);
      configFilter.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          updateConfig();
        }
      });
    }
    updateConfigViewer("");
    toggleVendor();
    populateThemeSelectors();
    applyTheme();
    highlightAll((storageGet(HL_KEY, "on") || "on") === "on");
    attachTypeahead();
    const queryState = loadState();
    refreshMeta();
    ensureHistoryVisibility();
    activateTab(activeTab, true);
    if (queryState && shouldAutoRun(queryState)) {
      triggerRun();
    }

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
    loadConfigText();

    window.addEventListener("popstate", () => {
      const state = parseQueryState();
      if (state && applyState(state)) {
        const snapshot = gatherState();
        storageSet("acl_state", JSON.stringify(snapshot));
        activateTab(activeTab, true);
        refreshMeta();
        if (activeTab === "config") {
          loadConfigText();
        }
        if (shouldAutoRun(state)) {
          triggerRun();
        }
        return;
      }
      const fallbackState = loadState();
      activateTab(activeTab, true);
      refreshMeta();
      if (activeTab === "config") {
        loadConfigText();
      }
      const snapshot = fallbackState || gatherState();
      if (shouldAutoRun(snapshot)) {
        triggerRun();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
