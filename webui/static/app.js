(() => {
  const THEMES = window.ACL_THEMES || [];
  const CONFIG_OPTIONS = window.ACL_CONFIG_OPTIONS || { asa: [], fortigate: [] };
  const HISTORY_ENABLED = window.ACL_HISTORY_ENABLED !== false;
  const SEARCH_LIMIT = window.ACL_SEARCH_LIMIT || 50;
  let previewSpeed = Number(window.ACL_THEME_PREVIEW_SPEED || 12);
  if (!Number.isFinite(previewSpeed) || previewSpeed <= 0) {
    previewSpeed = 12;
  }
  const THEME_PREVIEW_SPEED = previewSpeed;

  const PREF_COOKIE = "acl_theme_pref";
  const THEME_KEY = "acl_theme";
  const HL_KEY = "acl_highlight";
  const HIST_VIS_KEY = "acl_history_visible";

  const PREF_KEYS = {
    lineNumbers: "pref_line_numbers",
    wrapResults: "pref_wrap_results",
    configContext: "pref_config_context",
    configContextLines: "pref_config_context_lines",
    configMinChars: "pref_config_min_chars",
    configRegex: "pref_config_regex",
    showBeta: "pref_show_beta",
    fontBody: "pref_font_body",
    fontMono: "pref_font_mono",
    fontScale: "pref_font_scale",
    layoutWidth: "pref_layout_width",
  };

  const PREF_DEFAULTS = {
    lineNumbers: true,
    wrapResults: true,
    configContext: false,
    configContextLines: 3,
    configMinChars: 4,
    configRegex: false,
    showBeta: true,
    fontBody: "auto",
    fontMono: "auto",
    fontScale: 100,
    layoutWidth: 100,
  };

  const BODY_FONT_OPTIONS = {
    auto: "system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',sans-serif",
    inter: "'Inter','Helvetica Neue',Arial,sans-serif",
    atkinson: "'Atkinson Hyperlegible','Helvetica Neue',Arial,sans-serif",
    roboto: "'Roboto','Helvetica Neue',Arial,sans-serif",
    source: "'Source Sans 3','Helvetica Neue',Arial,sans-serif",
    serif: "Georgia,'Times New Roman',serif",
  };

  const MONO_FONT_OPTIONS = {
    auto: "'SFMono-Regular',Menlo,Consolas,'Liberation Mono',monospace",
    jetbrains: "'JetBrains Mono','Fira Code','SFMono-Regular',Consolas,monospace",
    fira: "'Fira Code','SFMono-Regular',Consolas,monospace",
    ibmplex: "'IBM Plex Mono','SFMono-Regular',Consolas,monospace",
    inconsolata: "'Inconsolata','SFMono-Regular',Consolas,monospace",
    courier: "'Courier New','Courier',monospace",
  };

  function computeAutoLayout() {
    const viewport = Math.max(window.innerWidth || 0, (window.screen && window.screen.width) || 0, 0);
    const dpr = window.devicePixelRatio || 1;
    let width = 900;
    if (viewport >= 2400) {
      width = 1280;
    } else if (viewport >= 2000) {
      width = 1160;
    } else if (viewport >= 1680) {
      width = 1040;
    } else if (viewport <= 1120) {
      width = 780;
    }
    let scale = 1.0;
    if (viewport >= 2000) {
      scale += 0.08;
    } else if (viewport >= 1600) {
      scale += 0.05;
    } else if (viewport <= 1120) {
      scale -= 0.05;
    }
    if (dpr >= 1.5) {
      scale += 0.05;
    } else if (dpr <= 1) {
      scale -= 0.02;
    }
    scale = clamp(scale, 0.85, 1.25);
    return { width, scale };
  }

  let autoLayout = computeAutoLayout();

  let activeTab = "rules";
  let stateGuard = false;
  let themePref = {};
  let prefs = { ...PREF_DEFAULTS };
  let prefGuard = false;
  let viewerGuard = false;
  const BETA_MODULES = new Set(
    (Array.isArray(window.ACL_BETA_MODULES) ? window.ACL_BETA_MODULES : [])
      .map((name) => (name === null || name === undefined ? "" : String(name).toLowerCase()))
      .filter((name) => name)
  );

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

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function prefStorageKey(key) {
    return `acl_pref_${key}`;
  }

  function readBoolPref(key, defaultValue) {
    const stored = storageGet(prefStorageKey(key), null);
    if (stored === null) {
      return defaultValue;
    }
    return parseBool(stored, defaultValue);
  }

  function readNumberPref(key, defaultValue, min, max) {
    const stored = storageGet(prefStorageKey(key), null);
    if (stored === null) {
      return defaultValue;
    }
    const parsed = parseInt(stored, 10);
    if (Number.isNaN(parsed)) {
      return defaultValue;
    }
    return clamp(parsed, min, max);
  }

  function readStringPref(key, defaultValue, allowed) {
    const stored = storageGet(prefStorageKey(key), null);
    if (stored === null || stored === "") {
      return defaultValue;
    }
    const value = String(stored);
    if (Array.isArray(allowed) && allowed.length > 0) {
      return allowed.includes(value) ? value : defaultValue;
    }
    return value;
  }

  function loadPrefs() {
    prefs = { ...PREF_DEFAULTS };
    prefs.lineNumbers = readBoolPref(PREF_KEYS.lineNumbers, PREF_DEFAULTS.lineNumbers);
    prefs.wrapResults = readBoolPref(PREF_KEYS.wrapResults, PREF_DEFAULTS.wrapResults);
    prefs.configContext = readBoolPref(PREF_KEYS.configContext, PREF_DEFAULTS.configContext);
    prefs.configContextLines = readNumberPref(
      PREF_KEYS.configContextLines,
      PREF_DEFAULTS.configContextLines,
      0,
      20
    );
    prefs.configMinChars = readNumberPref(
      PREF_KEYS.configMinChars,
      PREF_DEFAULTS.configMinChars,
      1,
      20
    );
    prefs.configRegex = readBoolPref(PREF_KEYS.configRegex, PREF_DEFAULTS.configRegex);
    prefs.showBeta = readBoolPref(PREF_KEYS.showBeta, PREF_DEFAULTS.showBeta);
    prefs.fontBody = readStringPref(
      PREF_KEYS.fontBody,
      PREF_DEFAULTS.fontBody,
      Object.keys(BODY_FONT_OPTIONS)
    );
    prefs.fontMono = readStringPref(
      PREF_KEYS.fontMono,
      PREF_DEFAULTS.fontMono,
      Object.keys(MONO_FONT_OPTIONS)
    );
    prefs.fontScale = readNumberPref(PREF_KEYS.fontScale, PREF_DEFAULTS.fontScale, 70, 150);
    prefs.layoutWidth = readNumberPref(PREF_KEYS.layoutWidth, PREF_DEFAULTS.layoutWidth, 60, 160);
  }

  function savePreference(key, value) {
    const storageKey = prefStorageKey(PREF_KEYS[key]);
    if (!storageKey) {
      return;
    }
    if (typeof value === "boolean") {
      storageSet(storageKey, value ? "1" : "0");
    } else {
      storageSet(storageKey, String(value));
    }
  }

  function syncPreferenceControls() {
    prefGuard = true;
    try {
      const ln = document.getElementById("pref_line_numbers");
      if (ln) {
        ln.checked = !!prefs.lineNumbers;
      }
      const wrap = document.getElementById("pref_wrap_results");
      if (wrap) {
        wrap.checked = !!prefs.wrapResults;
      }
      const cfgDefault = document.getElementById("pref_config_context_default");
      if (cfgDefault) {
        cfgDefault.checked = !!prefs.configContext;
      }
      const cfgLines = document.getElementById("pref_config_context_lines");
      if (cfgLines) {
        cfgLines.value = prefs.configContextLines;
      }
      const cfgMin = document.getElementById("pref_config_min_chars");
      if (cfgMin) {
        cfgMin.value = prefs.configMinChars;
      }
      const cfgRegex = document.getElementById("pref_config_regex");
      if (cfgRegex) {
        cfgRegex.checked = !!prefs.configRegex;
      }
      const beta = document.getElementById("pref_show_beta");
      if (beta) {
        beta.checked = !!prefs.showBeta;
      }
      const fontBody = document.getElementById("pref_font_body");
      if (fontBody) {
        fontBody.value = prefs.fontBody;
      }
      const fontMono = document.getElementById("pref_font_mono");
      if (fontMono) {
        fontMono.value = prefs.fontMono;
      }
      const fontScale = document.getElementById("pref_font_scale");
      if (fontScale) {
        fontScale.value = prefs.fontScale;
      }
      const layoutWidth = document.getElementById("pref_layout_width");
      if (layoutWidth) {
        layoutWidth.value = prefs.layoutWidth;
      }
      styleFontOptionPreviews();
    } finally {
      prefGuard = false;
    }
  }

  function syncConfigControls() {
    prefGuard = true;
    try {
      const contextToggle = document.getElementById("config_filter_context_toggle");
      if (contextToggle) {
        contextToggle.checked = !!prefs.configContext;
      }
      const contextLines = document.getElementById("config_filter_context_lines");
      if (contextLines) {
        contextLines.value = prefs.configContextLines;
      }
      const minChars = document.getElementById("config_filter_min_chars");
      if (minChars) {
        minChars.value = prefs.configMinChars;
      }
      const regexToggle = document.getElementById("config_filter_regex");
      if (regexToggle) {
        regexToggle.checked = !!prefs.configRegex;
      }
    } finally {
      prefGuard = false;
    }
  }

  function resolveFont(option, library, fallback) {
    if (!option) {
      return fallback;
    }
    const key = option in library ? option : option.toLowerCase();
    return library[key] || fallback;
  }

  function updateLayoutMetrics(tempScale, tempWidth) {
    const scaleLabel = document.getElementById("pref_font_scale_value");
    if (scaleLabel) {
      const value =
        tempScale !== undefined && tempScale !== null
          ? clamp(Number(tempScale), 70, 150)
          : clamp(prefs.fontScale, 70, 150);
      scaleLabel.textContent = `${value}%`;
    }
    const widthLabel = document.getElementById("pref_layout_width_value");
    if (widthLabel) {
      const value =
        tempWidth !== undefined && tempWidth !== null
          ? clamp(Number(tempWidth), 60, 160)
          : clamp(prefs.layoutWidth, 60, 160);
      widthLabel.textContent = `${value}%`;
    }
  }

  function applyLayoutPrefs() {
    const root = document.documentElement;
    const fontScale = clamp(prefs.fontScale || 100, 70, 150) / 100;
    const widthScale = clamp(prefs.layoutWidth || 100, 60, 160) / 100;
    const computedScale = +(autoLayout.scale * fontScale).toFixed(3);
    const computedWidth = Math.round(autoLayout.width * widthScale);
    root.style.setProperty("--font-scale", computedScale);
    root.style.setProperty("--content-width", `${computedWidth}px`);
    const bodyFont = resolveFont(prefs.fontBody, BODY_FONT_OPTIONS, BODY_FONT_OPTIONS.auto);
    const monoFont = resolveFont(prefs.fontMono, MONO_FONT_OPTIONS, MONO_FONT_OPTIONS.auto);
    root.style.setProperty("--font-body", bodyFont);
    root.style.setProperty("--font-mono", monoFont);
    updateLayoutMetrics();
    const preview = document.getElementById("theme_preview_box");
    if (preview) {
      preview.style.setProperty("--preview-body-font", bodyFont);
      preview.style.setProperty("--preview-mono-font", monoFont);
      preview
        .querySelectorAll("code")
        .forEach((node) => {
          node.style.fontFamily = monoFont;
        });
    }
    updateThemePreviewBox();
  }

  function refreshAutoLayout(force = false) {
    const next = computeAutoLayout();
    const widthDelta = Math.abs(next.width - autoLayout.width);
    const scaleDelta = Math.abs(next.scale - autoLayout.scale);
    if (!force && widthDelta < 8 && scaleDelta < 0.01) {
      return;
    }
    autoLayout = next;
    applyLayoutPrefs();
  }

  function applyPrefs() {
    document.body.classList.toggle("wrap-results", !!prefs.wrapResults);
    ensurePreLanguage(document);
    syncConfigControls();
    const highlightToggle = document.getElementById("hlToggle");
    const enableHighlight = highlightToggle ? highlightToggle.checked : true;
    refreshHighlights(enableHighlight);
    updateConfigViewer(document.getElementById("config_filter")?.value || "");
    refreshBetaVisibility();
    applyLayoutPrefs();
  }

  function styleFontOptionPreviews() {
    const applyStyles = (select, library) => {
      if (!select) {
        return;
      }
      Array.from(select.options).forEach((opt) => {
        const key = opt.value;
        const family = resolveFont(key, library, library.auto);
        opt.style.fontFamily = family;
      });
    };
    applyStyles(document.getElementById("pref_font_body"), BODY_FONT_OPTIONS);
    applyStyles(document.getElementById("pref_font_mono"), MONO_FONT_OPTIONS);
  }

  function clearResultsForTab(tab) {
    if (!tab) {
      return;
    }
    document.querySelectorAll(`.results[data-tab='${tab}']`).forEach((panel) => {
      panel.innerHTML = "";
    });
  }

  function clearTab(tab) {
    if (!tab) {
      return;
    }
    switch (tab) {
      case "rules": {
        const inspectField = document.getElementById("inspect");
        if (inspectField) {
          inspectField.value = "";
        }
        const oldField = document.getElementById("old");
        if (oldField) {
          oldField.value = "";
        }
        const newField = document.getElementById("new");
        if (newField) {
          newField.value = "";
        }
        const dportField = document.querySelector("input[name='dport']");
        if (dportField) {
          dportField.value = "";
        }
        const protoSelect = document.querySelector("select[name='proto']");
        if (protoSelect) {
          protoSelect.value = "";
        }
        const includeAny = document.getElementById("include_any");
        if (includeAny) {
          includeAny.checked = false;
        }
        const historyReplay = document.getElementById("history_replay");
        if (historyReplay) {
          historyReplay.value = "0";
        }
        setMode("inspect");
        break;
      }
      case "find": {
        const findField = document.getElementById("findq");
        if (findField) {
          findField.value = "";
        }
        const verboseToggle = document.getElementById("find_verbose");
        if (verboseToggle) {
          verboseToggle.checked = false;
        }
        break;
      }
      case "packet": {
        const pktSrc = document.getElementById("pkt_src");
        if (pktSrc) {
          pktSrc.value = "";
        }
        const pktDst = document.getElementById("pkt_dst");
        if (pktDst) {
          pktDst.value = "";
        }
        break;
      }
      case "packet-probe": {
        const probeSrc = document.getElementById("probe_src");
        if (probeSrc) {
          probeSrc.value = "";
        }
        const probeDst = document.getElementById("probe_dst");
        if (probeDst) {
          probeDst.value = "";
        }
        const probeProto = document.getElementById("probe_proto");
        if (probeProto) {
          probeProto.value = "";
        }
        const probeDport = document.getElementById("probe_dport");
        if (probeDport) {
          probeDport.value = "";
        }
        const probeIncludeAny = document.getElementById("probe_include_any");
        if (probeIncludeAny) {
          probeIncludeAny.checked = false;
        }
        break;
      }
      default:
        break;
    }
    clearResultsForTab(tab);
    setHistoryReplayFlag(false);
    saveState();
  }

  function setPreference(key, value, source) {
    if (!(key in prefs)) {
      return;
    }
    let next = value;
    const current = prefs[key];
    if (typeof current === "boolean") {
      next = !!value;
    } else if (typeof current === "number") {
      const asNumber = parseInt(value, 10);
      if (Number.isNaN(asNumber)) {
        next = current;
      } else if (key === "configContextLines") {
        next = clamp(asNumber, 0, 20);
      } else if (key === "configMinChars") {
        next = clamp(asNumber, 1, 20);
      } else if (key === "fontScale") {
        next = clamp(asNumber, 70, 150);
      } else if (key === "layoutWidth") {
        next = clamp(asNumber, 60, 160);
      } else {
        next = asNumber;
      }
    } else if (typeof current === "string") {
      const cleaned = String(value || "").trim().toLowerCase();
      if (key === "fontBody") {
        next = cleaned && BODY_FONT_OPTIONS[cleaned] ? cleaned : "auto";
      } else if (key === "fontMono") {
        next = cleaned && MONO_FONT_OPTIONS[cleaned] ? cleaned : "auto";
      } else {
        next = cleaned || current;
      }
    }
    if (prefs[key] === next) {
      return;
    }
    prefs[key] = next;
    savePreference(key, next);
    if (source !== "prefs-ui") {
      syncPreferenceControls();
    }
    applyPrefs();
    if (source !== "config-ui") {
      syncConfigControls();
    }
    applyPrefs();
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

  function updateThemePreviewBox() {
    const box = document.getElementById("theme_preview_box");
    if (!box) {
      return;
    }
    const lightTheme = themeForKind("light");
    const darkTheme = themeForKind("dark");
    box.style.setProperty("--preview-speed", `${THEME_PREVIEW_SPEED}s`);
    const accentCandidate =
      (darkTheme && darkTheme.vars && darkTheme.vars.accent) ||
      (lightTheme && lightTheme.vars && lightTheme.vars.accent) ||
      getComputedStyle(document.documentElement).getPropertyValue("--accent");
    if (lightTheme && lightTheme.vars) {
      box.style.setProperty("--preview-light", lightTheme.vars.bg || "#f6f8fa");
    }
    if (darkTheme && darkTheme.vars) {
      box.style.setProperty("--preview-dark", darkTheme.vars.bg || "#0e1116");
    }
    if (accentCandidate) {
      box.style.setProperty("--preview-accent", accentCandidate.trim());
    }
    const lightName = document.getElementById("preview_light_name");
    if (lightName) {
      lightName.textContent = lightTheme ? lightTheme.name : "Default";
    }
    const darkName = document.getElementById("preview_dark_name");
    if (darkName) {
      darkName.textContent = darkTheme ? darkTheme.name : "Default";
    }
  }

  function updateThemePreview(_kind) {
    updateThemePreviewBox();
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
    updateThemePreviewBox();
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

  function highlightAsaLine(text) {
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

  function ensurePreLanguage(scope) {
    const root =
      scope && typeof scope.querySelectorAll === "function" ? scope : document;
    root.querySelectorAll("pre").forEach((pre) => {
      if (!pre.dataset.lang) {
        pre.dataset.lang = "plain";
      }
    });
  }

  function renderPre(pre, rawText, enableHighlight) {
    const lang = (pre.dataset.lang || "").toLowerCase();
    const lines = rawText.split("\n");
    let numbering = Array.isArray(pre.__lineNumbers) ? pre.__lineNumbers : null;
    if (!numbering && pre.dataset.lineNumbers) {
      numbering = pre.dataset.lineNumbers.split(",").map((value) => {
        if (!value) {
          return null;
        }
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
      });
      pre.__lineNumbers = numbering;
    }
    let matchNumbers =
      pre.__matchNumbers && typeof pre.__matchNumbers === "object"
        ? new Set(Array.from(pre.__matchNumbers))
        : null;
    if (!matchNumbers && pre.dataset.matchLines) {
      const parsedMatches = pre.dataset.matchLines
        .split(",")
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value));
      if (parsedMatches.length) {
        matchNumbers = new Set(parsedMatches);
        pre.__matchNumbers = matchNumbers;
      }
    }
    const renderLine = (line) => {
      if (!enableHighlight) {
        return escapeHtml(line);
      }
      if (lang === "asa") {
        return highlightAsaLine(line);
      }
      return escapeHtml(line);
    };
    const getLineNumber = (idx) => {
      if (!numbering) {
        return idx + 1;
      }
      const value = numbering[idx];
      if (value === null || value === undefined) {
        return null;
      }
      return Number(value);
    };
    if (prefs.lineNumbers) {
      const htmlLines = lines.map((line, idx) => {
        const labelValue = numbering ? numbering[idx] : idx + 1;
        const labelText = labelValue === null || labelValue === undefined ? "" : String(labelValue);
        const safeLabel = labelText ? escapeHtml(labelText) : "&nbsp;";
        const content = renderLine(line) || "&nbsp;";
        const isMatch = matchNumbers && labelValue !== null && labelValue !== undefined && matchNumbers.has(Number(labelValue));
        const lineClass = isMatch ? "line match-line" : "line";
        const txtClass = isMatch ? "txt config-match" : "txt";
        return `<span class='${lineClass}'><span class='ln'>${safeLabel}</span><span class='${txtClass}'>${content}</span></span>`;
      });
      pre.innerHTML = htmlLines.join("");
    } else {
      const htmlLines = lines.map((line, idx) => {
        const rendered = renderLine(line) || "&nbsp;";
        const lineNumber = getLineNumber(idx);
        const isMatch = matchNumbers && lineNumber !== null && matchNumbers.has(Number(lineNumber));
        if (isMatch) {
          return `<span class='config-match'>${rendered}</span>`;
        }
        return rendered;
      });
      if (enableHighlight && lang === "asa") {
        pre.innerHTML = htmlLines.join("\n");
      } else {
        pre.innerHTML = htmlLines.join("\n");
      }
    }
    pre.classList.toggle("line-numbers", !!prefs.lineNumbers);
    pre.classList.toggle("wrap", !!prefs.wrapResults);
    pre.dataset.raw = rawText;
  }

  function applyHighlight(pre, enable) {
    if (!pre.dataset.raw) {
      pre.dataset.raw = pre.textContent || "";
    }
    const raw = pre.dataset.raw || "";
    renderPre(pre, raw, enable);
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
    ensurePreLanguage(document);
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
    syncConfigViewerControls();
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

  function betaModuleEnabled(name) {
    if (!name) {
      return false;
    }
    return BETA_MODULES.has(String(name).toLowerCase());
  }

  function ensureActiveTabAvailable() {
    const activeButton = document.querySelector(`.mode-tabs .tab[data-tab='${activeTab}']`);
    if (activeButton && !activeButton.hidden) {
      return;
    }
    const fallback = document.querySelector(".mode-tabs .tab:not([hidden])");
    const fallbackTab = fallback ? fallback.dataset.tab : "rules";
    if (fallbackTab && fallbackTab !== activeTab) {
      activateTab(fallbackTab, true);
    }
  }

  function refreshBetaVisibility() {
    const showBeta = !!prefs.showBeta;
    document.querySelectorAll("[data-beta-module]").forEach((node) => {
      const module = node.dataset.betaModule;
      if (!module) {
        return;
      }
      const optional = node.dataset.betaOptional === "1";
      const available = betaModuleEnabled(module);
      const shouldShow = available && (!optional || showBeta);
      const wasHidden = node.hidden;
      node.hidden = !shouldShow;
      if (node.matches(".mode-tabs .tab")) {
        node.style.display = shouldShow ? "inline-flex" : "none";
        if (!shouldShow && node.classList.contains("active")) {
          node.classList.remove("active");
        }
      } else if (node.matches(".tab-panel")) {
        node.style.display = shouldShow ? "" : "none";
        if (!shouldShow && node.classList.contains("active")) {
          node.classList.remove("active");
        }
      } else {
        node.style.display = shouldShow ? "" : "none";
      }
      if (wasHidden && shouldShow && node.matches(".tab-panel")) {
        node.classList.remove("active");
      }
    });
    document.querySelectorAll("[data-beta-badge]").forEach((badge) => {
      const module = badge.dataset.betaBadge;
      if (!module) {
        return;
      }
      const host = badge.closest("[data-beta-module]");
      const optional = host ? host.dataset.betaOptional === "1" : true;
      const visible = betaModuleEnabled(module) && (!optional || showBeta);
      badge.hidden = !visible;
      badge.style.display = visible ? "inline-flex" : "none";
    });
    ensureActiveTabAvailable();
  }

  function mainVendor() {
    const vendorSelect = document.getElementById("vendor");
    return (vendorSelect ? vendorSelect.value : "asa").toLowerCase();
  }

  function getMainConfigSelect(vendor) {
    if (vendor === "fortigate") {
      return document.getElementById("config_ftg");
    }
    return document.getElementById("config");
  }

  function getConfigOptions(vendor) {
    const select = getMainConfigSelect(vendor);
    if (!select) {
      return [];
    }
    return Array.from(select.options)
      .filter((opt) => opt.value && !opt.disabled)
      .map((opt) => opt.value);
  }

  function populateViewerOptions(vendor) {
    const viewerSelect = document.getElementById("config_select_tab");
    if (!viewerSelect) {
      return;
    }
    const options = getConfigOptions(vendor);
    const mainSelect = getMainConfigSelect(vendor);
    const current = mainSelect ? mainSelect.value : "";
    viewerSelect.innerHTML = "";
    if (!options.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "(no configs found)";
      opt.disabled = true;
      viewerSelect.appendChild(opt);
      viewerSelect.value = "";
      if (mainSelect) {
        mainSelect.value = "";
      }
      return;
    }
    options.forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      viewerSelect.appendChild(opt);
    });
    if (current && options.includes(current)) {
      viewerSelect.value = current;
    } else {
      viewerSelect.value = options[0];
      if (mainSelect) {
        mainSelect.value = viewerSelect.value;
      }
    }
  }

  function syncConfigViewerControls() {
    if (viewerGuard) {
      return;
    }
    viewerGuard = true;
    try {
      const vendor = mainVendor();
      const viewerVendor = document.getElementById("config_vendor_tab");
      if (viewerVendor) {
        viewerVendor.value = vendor;
      }
      populateViewerOptions(vendor);
    } finally {
      viewerGuard = false;
    }
  }

  function updateRunActions(tab) {
    document.querySelectorAll(".actions-run").forEach((node) => {
      const shouldShow = node.dataset.tab === tab && ["rules", "find", "packet", "packet-probe"].includes(tab);
      node.style.display = shouldShow ? "block" : "none";
    });
  }

  function setHistoryReplayFlag(active) {
    const hidden = document.getElementById("history_replay");
    if (hidden) {
      hidden.value = active ? "1" : "0";
    }
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
        if (activeTab === "packet") {
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
        }
      } else if (normalizedTab === "packet-probe") {
        activateTab("packet-probe", true);
        if (activeTab === "packet-probe") {
          const [srcVal = "", dstVal = ""] = cleanQuery.split("->");
          const srcField = document.getElementById("probe_src");
          const dstField = document.getElementById("probe_dst");
          if (srcField) {
            srcField.value = srcVal;
          }
          if (dstField) {
            dstField.value = dstVal;
          }
        }
      } else {
        activateTab(normalizedTab, true);
      }
    } finally {
      stateGuard = false;
    }
    saveState();
    setHistoryReplayFlag(true);
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
    let nextTab = tab;
    const requestedButton = document.querySelector(`.mode-tabs .tab[data-tab='${nextTab}']`);
    if (!requestedButton || requestedButton.hidden) {
      nextTab = "rules";
    }
    activeTab = nextTab;
    const panels = document.querySelectorAll(".tab-panel");
    panels.forEach((panel) => panel.classList.toggle("active", !panel.hidden && panel.id === `tab-${nextTab}`));
    const buttons = document.querySelectorAll(".mode-tabs .tab");
    buttons.forEach((btn) => btn.classList.toggle("active", !btn.hidden && btn.dataset.tab === nextTab));
    const service = document.getElementById("service_filters");
    const includeAnyLabel = document.getElementById("include_any_label");
    const cfgSection = document.querySelector(".section-config");
    const modeInputHidden = document.getElementById("mode");
    if (cfgSection) {
      cfgSection.style.display =
        nextTab === "rules" || nextTab === "packet" || nextTab === "packet-probe" ? "block" : "none";
    }
    const searchRow = document.querySelector(".global-search");
    if (searchRow) {
      searchRow.style.display = nextTab === "rules" ? "block" : "none";
    }
    document.querySelectorAll(".results[data-tab]").forEach((panel) => {
      const isActive = panel.dataset.tab === nextTab;
      panel.style.display = isActive ? "block" : "none";
      panel.classList.toggle("active", isActive);
    });
    updateRunActions(nextTab);
    if (nextTab === "rules") {
      const selected = document.querySelector("input[name='rule_mode']:checked");
      const chosen = selected ? selected.value : "inspect";
      setMode(chosen);
      if (modeInputHidden) {
        modeInputHidden.value = chosen;
      }
      if (service) {
        service.style.display = "block";
      }
      if (includeAnyLabel) {
        includeAnyLabel.style.display = "inline-flex";
      }
    } else if (nextTab === "find") {
      setMode("find");
      if (modeInputHidden) {
        modeInputHidden.value = "find";
      }
      if (service) {
        service.style.display = "none";
      }
      if (includeAnyLabel) {
        includeAnyLabel.style.display = "none";
      }
    } else if (nextTab === "packet") {
      setMode("packet");
      if (modeInputHidden) {
        modeInputHidden.value = "packet";
      }
      if (service) {
        service.style.display = "block";
      }
      if (includeAnyLabel) {
        includeAnyLabel.style.display = "none";
      }
    } else if (nextTab === "packet-probe") {
      if (modeInputHidden) {
        modeInputHidden.value = "packet-probe";
      }
      if (service) {
        service.style.display = "none";
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
    if (nextTab === "config") {
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
    ["inspect", "old", "new", "pkt_src", "pkt_dst", "findq", "probe_src", "probe_dst"].forEach((id) => {
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
      find_verbose: document.getElementById("find_verbose") ? document.getElementById("find_verbose").checked : false,
      pkt_src: document.getElementById("pkt_src").value,
      pkt_dst: document.getElementById("pkt_dst").value,
      pkt_guess: document.getElementById("pkt_guess") ? document.getElementById("pkt_guess").checked : true,
      proto: document.querySelector("select[name='proto']").value,
      dport: document.querySelector("input[name='dport']").value,
      include_any: document.getElementById("include_any").checked,
      fuzzy: document.getElementById("fuzzy").checked,
      probe_src: document.getElementById("probe_src") ? document.getElementById("probe_src").value : "",
      probe_dst: document.getElementById("probe_dst") ? document.getElementById("probe_dst").value : "",
      probe_proto: document.getElementById("probe_proto") ? document.getElementById("probe_proto").value : "",
      probe_dport: document.getElementById("probe_dport") ? document.getElementById("probe_dport").value : "",
      probe_include_any: document.getElementById("probe_include_any") ? document.getElementById("probe_include_any").checked : false,
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
    if (state.find_verbose) {
      params.set("find_verbose", "1");
    }
    assign("pkt_src", state.pkt_src);
    assign("pkt_dst", state.pkt_dst);
    if (state.pkt_guess === false) {
      params.set("pkt_guess", "0");
    }
    assign("proto", state.proto);
    assign("dport", state.dport);
    if (state.include_any) {
      params.set("include_any", "1");
    }
    params.set("fuzzy", state.fuzzy ? "1" : "0");
    assign("probe_src", state.probe_src);
    assign("probe_dst", state.probe_dst);
    assign("probe_proto", state.probe_proto);
    assign("probe_dport", state.probe_dport);
    if (state.probe_include_any) {
      params.set("probe_include_any", "1");
    }
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
    if (params.has("find_verbose")) {
      state.find_verbose = parseBool(params.get("find_verbose"), false);
      hasValue = true;
    }
    take("pkt_src", "pkt_src");
    take("pkt_dst", "pkt_dst");
    if (params.has("pkt_guess")) {
      state.pkt_guess = parseBool(params.get("pkt_guess"), true);
      hasValue = true;
    }
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
    take("probe_src", "probe_src");
    take("probe_dst", "probe_dst");
    take("probe_proto", "probe_proto");
    take("probe_dport", "probe_dport");
    if (params.has("probe_include_any")) {
      state.probe_include_any = parseBool(params.get("probe_include_any"), false);
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
      if (payload.find_verbose !== undefined) {
        const verboseToggle = document.getElementById("find_verbose");
        if (verboseToggle) {
          verboseToggle.checked = !!payload.find_verbose;
        }
      }
      assign("pkt_src", payload.pkt_src);
      assign("pkt_dst", payload.pkt_dst);
      if (payload.pkt_guess !== undefined) {
        const guessToggle = document.getElementById("pkt_guess");
        if (guessToggle) {
          guessToggle.checked = !!payload.pkt_guess;
        }
      }
      assign("probe_src", payload.probe_src);
      assign("probe_dst", payload.probe_dst);
      assign("probe_proto", payload.probe_proto);
      assign("probe_dport", payload.probe_dport);
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
      const probeIncludeAny = document.getElementById("probe_include_any");
      if (probeIncludeAny && payload.probe_include_any !== undefined) {
        probeIncludeAny.checked = !!payload.probe_include_any;
      }
      const fuzzyToggle = document.getElementById("fuzzy");
      if (fuzzyToggle && payload.fuzzy !== undefined) {
        fuzzyToggle.checked = !!payload.fuzzy;
      }
      syncConfigViewerControls();
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
    const tabButton = document.querySelector(`.mode-tabs .tab[data-tab='${state.tab}']`);
    if (!tabButton || tabButton.hidden) {
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
    if (state.tab === "packet-probe") {
      return Boolean((state.probe_src || "").trim() && (state.probe_dst || "").trim());
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

  function setConfigLoading(active) {
    const indicator = document.getElementById("config_loading");
    if (!indicator) {
      return;
    }
    indicator.classList.toggle("active", !!active);
  }

  function updateConfigViewer(filterText) {
    const viewer = document.getElementById("config_text");
    if (!viewer) {
      return;
    }
    delete viewer.__matchNumbers;
    const notice = document.getElementById("config_filter_notice");
    const filterRaw = (filterText || "").trim();
    const regexToggle = document.getElementById("config_filter_regex");
    const useRegex = !!(regexToggle && regexToggle.checked);
    const filterLower = filterRaw.toLowerCase();
    const minChars = Math.max(1, prefs.configMinChars || 1);
    const allLines = currentConfigText ? currentConfigText.split("\n") : [];
    let displayLines = allLines;
    let numbering = null;
    let message = "";
    let regexObj = null;
    if (useRegex && filterRaw) {
      try {
        regexObj = new RegExp(filterRaw, "i");
      } catch (err) {
        displayLines = ["[invalid regex]"];
        numbering = [null];
        message = `Invalid regex: ${err.message || err}`;
        const outputText = displayLines.join("\n");
        viewer.textContent = outputText;
        viewer.dataset.raw = outputText;
        viewer.__lineNumbers = numbering;
        delete viewer.__matchNumbers;
        const nameDisplay = document.getElementById("config_name_display");
        if (nameDisplay) {
          const { config } = currentConfig();
          nameDisplay.textContent = config || "n/a";
        }
        if (notice) {
          notice.textContent = message;
        }
        const hlToggleErr = document.getElementById("hlToggle");
        const highlightEnabledErr = hlToggleErr
          ? hlToggleErr.checked
          : (storageGet(HL_KEY, "on") || "on") === "on";
        refreshHighlights(highlightEnabledErr);
        return;
      }
    }
    if (!currentConfigText) {
      displayLines = [];
      numbering = null;
      delete viewer.__matchNumbers;
      delete viewer.dataset.lineNumbers;
      delete viewer.dataset.matchLines;
    } else if (!filterRaw) {
      numbering = null;
      delete viewer.__matchNumbers;
      delete viewer.dataset.lineNumbers;
      delete viewer.dataset.matchLines;
    } else if (!useRegex && filterRaw.length < minChars) {
      const remaining = minChars - filterRaw.length;
      message = `Type ${remaining} more character${remaining === 1 ? "" : "s"} to filter (min ${minChars}).`;
      if (notice) {
        notice.textContent = message;
      }
      if ((viewer.dataset.raw || "") === currentConfigText) {
        const hlToggleShort = document.getElementById("hlToggle");
        const highlightEnabledShort = hlToggleShort
          ? hlToggleShort.checked
          : (storageGet(HL_KEY, "on") || "on") === "on";
        refreshHighlights(highlightEnabledShort);
        return;
      }
      numbering = null;
      delete viewer.__matchNumbers;
    } else {
      const matches = [];
      for (let idx = 0; idx < allLines.length; idx += 1) {
        const line = allLines[idx];
        const match = useRegex ? (regexObj ? regexObj.test(line) : false) : line.toLowerCase().includes(filterLower);
        if (match) {
          matches.push(idx);
        }
      }
      let matchNumbersForDisplay = null;
      if (!matches.length) {
        displayLines = ["[no matches]"];
        numbering = [null];
        message = "No matches found.";
        delete viewer.__matchNumbers;
      } else {
        const keep = new Set();
        if (prefs.configContext) {
          const span = prefs.configContextLines || 0;
          matches.forEach((idx) => {
            const start = Math.max(0, idx - span);
            const end = Math.min(allLines.length - 1, idx + span);
            for (let i = start; i <= end; i += 1) {
              keep.add(i);
            }
          });
        } else {
          matches.forEach((idx) => keep.add(idx));
        }
        const sorted = Array.from(keep).sort((a, b) => a - b);
        const outLines = [];
        const outNumbers = [];
        let prev = -2;
        sorted.forEach((idx) => {
          if (outLines.length && idx - prev > 1) {
            outLines.push("…");
            outNumbers.push(null);
          }
          outLines.push(allLines[idx]);
          outNumbers.push(idx + 1);
          prev = idx;
        });
        displayLines = outLines;
        numbering = outNumbers;
        matchNumbersForDisplay = new Set(matches.map((idx) => idx + 1));
        if (matchNumbersForDisplay.size) {
          viewer.__matchNumbers = matchNumbersForDisplay;
          viewer.dataset.matchLines = Array.from(matchNumbersForDisplay).join(",");
        } else {
          delete viewer.__matchNumbers;
          delete viewer.dataset.matchLines;
        }
      }
    }
    const outputText = displayLines.length ? displayLines.join("\n") : "";
    viewer.textContent = outputText;
    viewer.dataset.raw = outputText;
    if (numbering) {
      viewer.__lineNumbers = numbering;
      viewer.dataset.lineNumbers = numbering.map((value) => (value === null || value === undefined ? "" : String(value))).join(",");
    } else {
      delete viewer.__lineNumbers;
      delete viewer.dataset.lineNumbers;
    }
    const nameDisplay = document.getElementById("config_name_display");
    if (nameDisplay) {
      const { config } = currentConfig();
      nameDisplay.textContent = config || "n/a";
    }
    if (notice) {
      notice.textContent = message;
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
      setConfigLoading(false);
      return;
    }
    setConfigLoading(true);
    fetch(`/api/config?vendor=${vendor}&config=${encodeURIComponent(config)}`)
      .then((resp) => (resp.ok ? resp.json() : Promise.reject()))
      .then((data) => {
        currentConfigText = (data.text || "").replace(/\r\n?/g, "\n");
        updateConfigViewer(document.getElementById("config_filter")?.value || "");
      })
      .catch(() => {
        currentConfigText = "";
        updateConfigViewer("");
      })
      .finally(() => {
        setConfigLoading(false);
      });
  }

  function setRunResults(tab, htmlContent, meta) {
    let targetTab = tab || "rules";
    const tabButton = document.querySelector(`.mode-tabs .tab[data-tab='${targetTab}']`);
    if (!tabButton || tabButton.hidden) {
      targetTab = "rules";
    }
    let container = document.querySelector(`.results[data-tab='${targetTab}']`);
    if (!container && targetTab !== "rules") {
      targetTab = "rules";
      container = document.querySelector(".results[data-tab='rules']");
    }
    if (container) {
      container.innerHTML = htmlContent || "";
      ensurePreLanguage(container);
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
        if (meta.guess_pairs !== undefined) {
          const guessToggle = document.getElementById("pkt_guess");
          if (guessToggle) {
            guessToggle.checked = !!meta.guess_pairs;
          }
        }
      }
    }
  }

  function probeResultsContainer() {
    return document.querySelector(".results[data-tab='packet-probe']");
  }

  function setProbeResults(htmlContent) {
    const container = probeResultsContainer();
    if (container) {
      container.innerHTML = htmlContent;
      ensurePreLanguage(container);
    }
    const highlightToggle = document.getElementById("hlToggle");
    const enable = highlightToggle ? highlightToggle.checked : true;
    highlightAll(enable);
  }

  function renderProbeResult(configName, payload) {
    if (!payload || typeof payload !== "object") {
      return `<div class="section"><p style="color:red">No data returned.</p></div>`;
    }
    const result = payload.result || {};
    const allowed = result.allowed ? "ALLOWED" : "BLOCKED";
    const nat = result.nat || {};
    const acl = result.acl || {};
    const context = result.context || {};
    const resolved = result.resolved || {};
    const input = result.input || {};
    const natLines = [];
    if (nat.applied) {
      const rule = nat.rule || {};
      natLines.push(`Rule: ${rule.raw ? escapeHtml(rule.raw) : "(unknown)"}`);
      const tx = nat.translations || {};
      if (tx.src) {
        natLines.push(`Source: ${escapeHtml(String(tx.src.before || ""))} -> ${escapeHtml(String(tx.src.after || ""))}`);
        if (tx.src.note) {
          natLines.push(`  note: ${escapeHtml(String(tx.src.note))}`);
        }
      }
      if (tx.dst) {
        natLines.push(`Destination: ${escapeHtml(String(tx.dst.before || ""))} -> ${escapeHtml(String(tx.dst.after || ""))}`);
        if (tx.dst.note) {
          natLines.push(`  note: ${escapeHtml(String(tx.dst.note))}`);
        }
      }
    } else {
      natLines.push("No NAT rule matched.");
    }
    const matches = (acl.matches || []).slice(0, 200).map((match) => {
      const raw = escapeHtml(match.raw || "");
      const summary = escapeHtml(match.summary || "");
      return `  ${raw}\n   -> ${summary}`;
    });
    const aclText = matches.length ? matches.join("\n") : "  (no ACL matches)";
    const candidateLines = (context.acl_candidates || []).map((cand) => {
      const iface = cand.interface || cand.display_interface || "(unknown)";
      const direction = cand.direction || cand.display_direction || "";
      return `  ${escapeHtml(String(iface))}${direction ? ` (${escapeHtml(String(direction))})` : ""}`;
    });
    const candidateBlock = candidateLines.length
      ? `<div class='diff diff-aliases'><h3>ACL Candidate Bindings</h3><pre>${candidateLines.join("\n")}</pre></div>`
      : "";
    const jsonPretty = escapeHtml(JSON.stringify(result, null, 2));
    return `
<div class='results results-probe' data-tab='packet-probe'>
  <div class='section'><h2>${escapeHtml(configName || "")}</h2><h3>Packet Probe</h3>
  <p>Status: ${allowed}</p>
  <p>Input: src=${escapeHtml(String(input.src || ""))} dst=${escapeHtml(String(input.dst || ""))} proto=${escapeHtml(String(input.proto || 'any'))} dports=${escapeHtml(String((input.dports || []).join(', ') || 'any'))}</p>
  <p>Resolved: src=${escapeHtml(String(resolved.src || ""))} -> ${escapeHtml(String(resolved.post_nat_src || ""))} | dst=${escapeHtml(String(resolved.dst || ""))} -> ${escapeHtml(String(resolved.post_nat_dst || ""))}</p></div>
  <div class='diff diff-added'><h3>NAT Evaluation</h3><pre>${natLines.join("\n")}\n</pre></div>
  ${candidateBlock}
  <div class='diff diff-raw'><h3>ACL Matches</h3><pre data-lang='asa'>${aclText}</pre></div>
  <div class='diff diff-json'><h3>Raw Result</h3><pre>${jsonPretty}</pre></div>
</div>
`;
  }

  async function runPacketProbe(formData) {
    const container = probeResultsContainer();
    if (!container) {
      return;
    }
    container.innerHTML = "<div class='section'><p>Running packet probe…</p></div>";
    const { vendor, config } = currentConfig();
    if (!config) {
      setProbeResults("<div class='section'><p style='color:red'>Select a config before running the probe.</p></div>");
      return;
    }
    const payload = {
      vendor,
      config,
      src: String(formData.get("probe_src") || "").trim(),
      dst: String(formData.get("probe_dst") || "").trim(),
      proto: String(formData.get("probe_proto") || "").trim(),
      dports: [],
      include_any: document.getElementById("probe_include_any")?.checked || false,
    };
    const dportRaw = String(formData.get("probe_dport") || "").trim();
    if (dportRaw) {
      payload.dports = dportRaw.split(",").map((part) => part.trim()).filter((part) => part);
    }
    if (!payload.src || !payload.dst) {
      setProbeResults("<div class='section'><p style='color:red'>Source and destination are required.</p></div>");
      return;
    }
    try {
      const resp = await fetch("/api/probe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (!resp.ok || data.error) {
        const err = (data && data.error) || `Probe failed (HTTP ${resp.status})`;
        setProbeResults(`<div class='section'><p style='color:red'>${escapeHtml(String(err))}</p></div>`);
        return;
      }
      setProbeResults(renderProbeResult(data.config || config, data));
    } catch (err) {
      setProbeResults(`<div class='section'><p style='color:red'>Probe request failed: ${escapeHtml(String(err))}</p></div>`);
    }
  }

  function updateDebugStatus(message, isError = false) {
    const statusElem = document.getElementById("debug_status");
    if (!statusElem) {
      return;
    }
    statusElem.textContent = message;
    statusElem.style.color = isError ? "#ff7b72" : "var(--sub)";
  }

  async function flushServerCache(includeDisk = true) {
    updateDebugStatus("Flushing server caches…");
    try {
      const resp = await fetch("/api/cache/flush", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ disk: includeDisk }),
      });
      const data = await resp.json();
      if (!resp.ok || data.error) {
        updateDebugStatus((data && data.error) || `Flush failed (HTTP ${resp.status})`, true);
        return;
      }
      updateDebugStatus("Server caches flushed.");
      listHistory();
    } catch (err) {
      updateDebugStatus(`Flush failed: ${err}`, true);
    }
  }

  function clearClientCache() {
    updateDebugStatus("Clearing browser cache…");
    try {
      if (typeof window !== "undefined" && window.localStorage) {
        const storage = window.localStorage;
        const removeKeys = [];
        for (let i = 0; i < storage.length; i += 1) {
          const key = storage.key(i);
          if (!key) {
            continue;
          }
          if (key === THEME_KEY || key === HL_KEY || key.startsWith("acl_")) {
            removeKeys.push(key);
          }
        }
        removeKeys.forEach((key) => {
          try {
            storage.removeItem(key);
          } catch (err) {
            console.warn("Failed to remove key", key, err);
          }
        });
      }
      if (typeof document !== "undefined") {
        document.cookie = `${PREF_COOKIE}=;path=/;max-age=0`;
      }
      updateDebugStatus("Browser cache cleared. Reloading…");
      setTimeout(() => window.location.reload(), 750);
    } catch (err) {
      updateDebugStatus(`Clear failed: ${err}`, true);
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
    const modeValue = formData.get("mode");
    if (modeValue === "packet-probe") {
      try {
        await runPacketProbe(formData);
        saveState();
        listHistory();
      } finally {
        setHistoryReplayFlag(false);
      }
      return;
    }
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
    } finally {
      setHistoryReplayFlag(false);
    }
  }

  function triggerRun() {
    const form = document.forms[0];
    if (!form) {
      setHistoryReplayFlag(false);
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
    loadPrefs();
    refreshAutoLayout(true);
    populateConfigs();
    syncConfigViewerControls();
    const configVendorTab = document.getElementById("config_vendor_tab");
    if (configVendorTab) {
      configVendorTab.addEventListener("change", () => {
        const vendor = (configVendorTab.value || "asa").toLowerCase();
        const vendorSelect = document.getElementById("vendor");
        if (vendorSelect && vendorSelect.value !== vendor) {
          vendorSelect.value = vendor;
        }
        toggleVendor();
        loadConfigText();
        refreshMeta();
        saveState();
      });
    }
    const configSelectTab = document.getElementById("config_select_tab");
    if (configSelectTab) {
      configSelectTab.addEventListener("change", () => {
        const vendor =
          (document.getElementById("config_vendor_tab")?.value || mainVendor()).toLowerCase();
        const vendorSelect = document.getElementById("vendor");
        if (vendorSelect && vendorSelect.value !== vendor) {
          vendorSelect.value = vendor;
          toggleVendor();
        }
        const mainSelect = getMainConfigSelect(vendor);
        if (mainSelect && mainSelect.value !== configSelectTab.value) {
          mainSelect.value = configSelectTab.value;
        }
        loadConfigText();
        refreshMeta();
        saveState();
      });
    }
    ["config", "config_ftg"].forEach((id) => {
      const select = document.getElementById(id);
      if (select) {
        select.addEventListener("change", () => {
          syncConfigViewerControls();
          loadConfigText();
          refreshMeta();
        });
      }
    });
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
    loadConfigText();
    populateThemeSelectors();
    applyTheme();
    syncPreferenceControls();
    syncConfigControls();
    const highlightDefault = (storageGet(HL_KEY, "on") || "on") === "on";
    const hlToggleInitial = document.getElementById("hlToggle");
    if (hlToggleInitial) {
      hlToggleInitial.checked = highlightDefault;
    }
    highlightAll(highlightDefault);
    applyPrefs();
    attachTypeahead();
    const queryState = loadState();
    syncConfigViewerControls();
    loadConfigText();
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
      hlToggle.addEventListener("change", toggleHighlight);
    }
    const histToggle = document.getElementById("histToggle");
    if (histToggle) {
      histToggle.addEventListener("click", toggleHistory);
      histToggle.style.display = HISTORY_ENABLED ? "inline-flex" : "none";
    }
    document.getElementById("vendor").addEventListener("change", () => {
      toggleVendor();
      loadConfigText();
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

    const prefLineNumbers = document.getElementById("pref_line_numbers");
    if (prefLineNumbers) {
      prefLineNumbers.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("lineNumbers", event.target.checked, "prefs-ui");
      });
    }
    const prefWrapResults = document.getElementById("pref_wrap_results");
    if (prefWrapResults) {
      prefWrapResults.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("wrapResults", event.target.checked, "prefs-ui");
      });
    }
    const prefConfigContextDefault = document.getElementById("pref_config_context_default");
    if (prefConfigContextDefault) {
      prefConfigContextDefault.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("configContext", event.target.checked, "prefs-ui");
      });
    }
    const prefConfigContextLines = document.getElementById("pref_config_context_lines");
    if (prefConfigContextLines) {
      prefConfigContextLines.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("configContextLines", event.target.value, "prefs-ui");
      });
    }
    const prefConfigMinChars = document.getElementById("pref_config_min_chars");
    if (prefConfigMinChars) {
      prefConfigMinChars.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("configMinChars", event.target.value, "prefs-ui");
      });
    }
    const prefConfigRegex = document.getElementById("pref_config_regex");
    if (prefConfigRegex) {
      prefConfigRegex.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("configRegex", event.target.checked, "prefs-ui");
        updateConfigViewer(document.getElementById("config_filter")?.value || "");
      });
    }
    const prefShowBeta = document.getElementById("pref_show_beta");
    if (prefShowBeta) {
      prefShowBeta.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("showBeta", event.target.checked, "prefs-ui");
      });
    }
    const prefFontBody = document.getElementById("pref_font_body");
    if (prefFontBody) {
      prefFontBody.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("fontBody", event.target.value, "prefs-ui");
      });
    }
    const prefFontMono = document.getElementById("pref_font_mono");
    if (prefFontMono) {
      prefFontMono.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("fontMono", event.target.value, "prefs-ui");
      });
    }
    const prefFontScale = document.getElementById("pref_font_scale");
    if (prefFontScale) {
      prefFontScale.addEventListener("input", (event) => {
        if (prefGuard) {
          return;
        }
        updateLayoutMetrics(event.target.value, undefined);
      });
      prefFontScale.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("fontScale", event.target.value, "prefs-ui");
      });
    }
    const prefLayoutWidth = document.getElementById("pref_layout_width");
    if (prefLayoutWidth) {
      prefLayoutWidth.addEventListener("input", (event) => {
        if (prefGuard) {
          return;
        }
        updateLayoutMetrics(undefined, event.target.value);
      });
      prefLayoutWidth.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("layoutWidth", event.target.value, "prefs-ui");
      });
    }
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      const controls = panel.querySelector(".tab-controls");
      if (controls) {
        panel.insertBefore(controls, panel.firstChild);
      }
    });
    document.querySelectorAll("button[data-clear-tab]").forEach((btn) => {
      btn.addEventListener("click", () => clearTab(btn.dataset.clearTab || ""));
    });
    const configContextToggle = document.getElementById("config_filter_context_toggle");
    if (configContextToggle) {
      configContextToggle.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("configContext", event.target.checked, "config-ui");
      });
    }
    const configContextLines = document.getElementById("config_filter_context_lines");
    if (configContextLines) {
      configContextLines.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("configContextLines", event.target.value, "config-ui");
      });
    }
    const configMinChars = document.getElementById("config_filter_min_chars");
    if (configMinChars) {
      configMinChars.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("configMinChars", event.target.value, "config-ui");
      });
    }
    const configRegexToggle = document.getElementById("config_filter_regex");
    if (configRegexToggle) {
      configRegexToggle.addEventListener("change", (event) => {
        if (prefGuard) {
          return;
        }
        setPreference("configRegex", event.target.checked, "config-ui");
        updateConfigViewer(document.getElementById("config_filter")?.value || "");
      });
    }

    loadConfigText();

    const resizeHandler = debounce(() => refreshAutoLayout(false), 200);
    window.addEventListener("resize", resizeHandler);

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

    const debugFlush = document.getElementById("debug_flush_server");
    if (debugFlush) {
      debugFlush.addEventListener("click", () => flushServerCache(true));
    }
    const debugClear = document.getElementById("debug_clear_client");
    if (debugClear) {
      debugClear.addEventListener("click", clearClientCache);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
