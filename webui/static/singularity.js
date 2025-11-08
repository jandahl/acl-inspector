const DATA = window.SINGULARITY_DATA || {};

const state = {
  mode: (DATA.defaultMode || 'fuzzy').toLowerCase(),
  selection: null,
  lastQuery: '',
};

const cache = {
  meta: new Map(),
};

const themePalettes = DATA.themes || {};
const themeNames = DATA.themeNames || {};
const THEME_KEY = DATA.themeStorageKey || 'acl.singularity.theme';
const DEFAULT_THEME = DATA.defaultTheme || (themePalettes.dark ? 'dark' : 'light');
let activeTheme = null;
let storedPreference = null;

const selectors = {
  query: document.querySelector('[data-role="query"]'),
  queryReset: document.querySelector('[data-role="query-reset"]'),
  hint: document.querySelector('[data-role="search-hint"]'),
  suggestions: document.querySelector('[data-role="suggestions"]'),
  suggestionBox: document.querySelector('.singularity-suggestions'),
  empty: document.querySelector('[data-role="empty-state"]'),
  error: document.querySelector('[data-role="error-state"]'),
  details: document.querySelector('[data-role="details"]'),
  detailsCard: document.querySelector('.details-card'),
  type: document.querySelector('[data-role="selected-type"]'),
  label: document.querySelector('[data-role="selected-label"]'),
  meta: document.querySelector('[data-role="selected-meta"]'),
  copy: document.querySelector('[data-role="copy-value"]'),
  reveal: document.querySelector('[data-role="reveal"]'),
  advanced: document.querySelector('[data-role="advanced"]'),
  themeToggle: document.querySelector('[data-role="theme-toggle"]'),
  settingsToggle: document.querySelector('[data-role="settings-toggle"]'),
  settingsOverlay: document.querySelector('[data-role="settings-overlay"]'),
  settingsClose: document.querySelector('[data-role="settings-close"]'),
  rankingPopularity: document.querySelector('[data-role="ranking-popularity"]'),
  rankingPopularityValue: document.querySelector('[data-role="ranking-popularity-value"]'),
  rankingHome: document.querySelector('[data-role="ranking-home"]'),
  rankingHomeValue: document.querySelector('[data-role="ranking-home-value"]'),
  motionForeground: document.querySelector('[data-role="motion-foreground"]'),
  motionForegroundValue: document.querySelector('[data-role="motion-foreground-value"]'),
  motionBackground: document.querySelector('[data-role="motion-background"]'),
  motionBackgroundValue: document.querySelector('[data-role="motion-background-value"]'),
};

const shell = document.querySelector('.singularity-shell');
const SEARCH_LIMIT = Number(DATA.searchLimit || 12) || 12;
let activeFetchToken = 0;
let activeSelection = null;
const settingsTabs = Array.from(document.querySelectorAll('[data-role="settings-tab"]'));
const settingsPanels = Array.from(document.querySelectorAll('[data-role="settings-panel"]'));

const PREFERENCES_KEY = 'acl.singularity.prefs';
const defaultPreferences = {
  ranking: {
    popularity: 0.6,
    home: 0.4,
  },
  motion: {
    foreground: 260,
    background: 120,
  },
};

let preferences = loadPreferences();
let settingsOpen = false;
let lastFocusedElement = null;
let lastSuggestions = [];
let isRendering = false;

function setStage(next) {
  if (!shell) {
    return;
  }
  const current = shell.dataset.stage || 'idle';
  if (current === next) {
    return;
  }
  shell.dataset.stage = next;
}

function invalidateActiveFetch() {
  activeFetchToken += 1;
}

function updateQueryResetVisibility(hasValue) {
  if (!selectors.queryReset) {
    return;
  }
  selectors.queryReset.hidden = !hasValue;
}

function clearQuery(event) {
  if (event) {
    event.preventDefault();
  }
  if (!selectors.query) {
    return;
  }
  selectors.query.value = '';
  updateQueryResetVisibility(false);
  if (typeof debouncedRequest?.cancel === 'function') {
    debouncedRequest.cancel();
  }
  invalidateActiveFetch();
  clearSuggestions();
  hideDetails();
  setStage('idle');
  selectors.query.focus();
}

function setToggleState(kind) {
  if (!selectors.themeToggle) {
    return;
  }
  const isLight = kind === 'light';
  selectors.themeToggle.setAttribute('aria-pressed', String(isLight));
  const themeName = themeNames[kind] || kind;
  selectors.themeToggle.setAttribute('title', `Theme: ${themeName}`);
}

function applyTheme(kind, persist = false) {
  if (!document.body || !themePalettes[kind]) {
    return false;
  }
  const palette = themePalettes[kind];
  Object.entries(palette).forEach(([token, value]) => {
    document.body.style.setProperty(`--sg-${token}`, value);
  });
  document.body.dataset.theme = kind;
  setToggleState(kind);
  activeTheme = kind;
  if (persist) {
    storedPreference = kind;
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem(THEME_KEY, kind);
      }
    } catch (err) {
      /* ignore storage errors */
    }
  }
  return true;
}

function readStoredTheme() {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      return window.localStorage.getItem(THEME_KEY);
    }
  } catch (err) {
    return null;
  }
  return null;
}

function resolveSystemTheme() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return null;
  }
  if (window.matchMedia('(prefers-color-scheme: light)').matches && themePalettes.light) {
    return 'light';
  }
  if (window.matchMedia('(prefers-color-scheme: dark)').matches && themePalettes.dark) {
    return 'dark';
  }
  return null;
}

function handleSystemThemeChange(event) {
  if (storedPreference) {
    return;
  }
  const next = event.matches ? 'dark' : 'light';
  if (themePalettes[next]) {
    applyTheme(next, false);
  }
}

function initThemeControls() {
  const stored = readStoredTheme();
  if (stored && themePalettes[stored]) {
    storedPreference = stored;
    applyTheme(stored, false);
  } else {
    const system = resolveSystemTheme();
    if (!applyTheme(system || DEFAULT_THEME, false)) {
      const first = Object.keys(themePalettes)[0];
      if (first) {
        applyTheme(first, false);
      }
    }
  }

  if (selectors.themeToggle) {
    selectors.themeToggle.addEventListener('click', () => {
      const kinds = Object.keys(themePalettes);
      if (!kinds.length) {
        return;
      }
      let next = 'light';
      if (activeTheme === 'light' && themePalettes.dark) {
        next = 'dark';
      } else if (activeTheme === 'dark' && themePalettes.light) {
        next = 'light';
      } else if (activeTheme && kinds.length > 1) {
        const index = kinds.indexOf(activeTheme);
        next = kinds[(index + 1) % kinds.length];
      } else if (!themePalettes[next]) {
        next = kinds[0];
      }
      applyTheme(next, true);
    });
  }

  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', handleSystemThemeChange);
    } else if (typeof media.addListener === 'function') {
      media.addListener(handleSystemThemeChange);
    }
  }

  if (!activeTheme && document.body) {
    const fallback = document.body.dataset.theme || DEFAULT_THEME;
    setToggleState(fallback);
  }
}

function hideDetails() {
  if (selectors.details) {
    selectors.details.classList.remove('is-visible');
    selectors.details.hidden = true;
  }
  if (selectors.copy) {
    selectors.copy.disabled = true;
    selectors.copy.removeAttribute('data-value');
  }
  if (selectors.reveal) {
    selectors.reveal.setAttribute('aria-expanded', 'false');
  }
  if (selectors.advanced) {
    selectors.advanced.hidden = true;
  }
  activeSelection = null;
  state.selection = null;
  const hasQuery = selectors.query && selectors.query.value && selectors.query.value.trim().length > 0;
  setStage(hasQuery ? 'searching' : 'idle');
}

function setSuggestionState(next) {
  if (selectors.suggestionBox) {
    selectors.suggestionBox.dataset.state = next;
  }
}

function clearSuggestions() {
  if (selectors.suggestions) {
    selectors.suggestions.innerHTML = '';
  }
  lastSuggestions = [];
  const stage = shell ? shell.dataset.stage : 'idle';
  if (selectors.empty) {
    selectors.empty.hidden = stage !== 'searching';
  }
  if (selectors.error) {
    selectors.error.hidden = true;
  }
  setSuggestionState('idle');
}

function describeType(kind) {
  switch ((kind || '').toLowerCase()) {
    case 'group':
      return 'Group';
    case 'literal':
      return 'Literal';
    case 'context':
      return 'Context';
    default:
      return 'Object';
  }
}

function clonePreferences(source) {
  return JSON.parse(JSON.stringify(source));
}

function loadPreferences() {
  const base = clonePreferences(defaultPreferences);
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      const raw = window.localStorage.getItem(PREFERENCES_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object') {
          if (parsed.ranking && typeof parsed.ranking === 'object') {
            if (!Number.isNaN(Number(parsed.ranking.popularity))) {
              base.ranking.popularity = Number(parsed.ranking.popularity);
            }
            if (!Number.isNaN(Number(parsed.ranking.home))) {
              base.ranking.home = Number(parsed.ranking.home);
            }
          }
          if (parsed.motion && typeof parsed.motion === 'object') {
            if (!Number.isNaN(Number(parsed.motion.foreground))) {
              base.motion.foreground = Number(parsed.motion.foreground);
            }
            if (!Number.isNaN(Number(parsed.motion.background))) {
              base.motion.background = Number(parsed.motion.background);
            }
          }
        }
      }
    }
  } catch (err) {
    /* ignore corrupted preferences */
  }
  return base;
}

function savePreferences() {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
    }
  } catch (err) {
    /* ignore storage failures */
  }
}

function getRankingWeights() {
  return preferences.ranking;
}

function formatWeight(value) {
  return Number.parseFloat(value).toFixed(1);
}

function computeItemScore(item, index) {
  const weights = getRankingWeights();
  const baseScore =
    typeof item.score === 'number'
      ? -item.score
      : -(typeof item.rank === 'number' ? item.rank : index);
  const popularitySignal =
    typeof item.popularity === 'number'
      ? item.popularity
      : Number((item.signals && item.signals.popularity) || 0);
  let scopeBoost = 0;
  if (item.home === 'home') {
    scopeBoost = weights.home;
  } else if (item.home === 'probable') {
    scopeBoost = weights.home * 0.5;
  }
  let queryBoost = 0;
  const query = (state.lastQuery || '').toLowerCase();
  if (query) {
    const label = String(item.label || item.value || '').toLowerCase();
    if (label === query) {
      queryBoost = 5;
    } else if (label.startsWith(query)) {
      queryBoost = 3;
    } else if (label.includes(query)) {
      queryBoost = 1.5;
    }
  }
  return baseScore + popularitySignal * weights.popularity + scopeBoost + queryBoost;
}

function rankSuggestions(items) {
  return (items || [])
    .map((entry, idx) => ({
      entry,
      idx,
      score: computeItemScore(entry, idx),
    }))
    .sort((a, b) => {
      if (b.score !== a.score) {
        return b.score - a.score;
      }
      return a.idx - b.idx;
    })
    .map((payload) => payload.entry);
}

function rerenderSuggestions() {
  if (!lastSuggestions.length || isRendering) {
    return;
  }
  if (shell && shell.dataset.stage === 'selected') {
    return;
  }
  renderSuggestions(lastSuggestions.slice());
}

function applyMotionPreferences() {
  const fg = preferences.motion.foreground;
  const stage = Math.round(fg * 1.05);
  const search = Math.round(fg * 1.2);
  const delayStep = Math.max(10, Math.round(fg / 8));
  const bg = preferences.motion.background;
  const halo = Math.round(bg * 1.1);
  if (document.body) {
    document.body.style.setProperty('--sg-motion-foreground', `${fg}ms`);
    document.body.style.setProperty('--sg-motion-stage', `${stage}ms`);
    document.body.style.setProperty('--sg-motion-search', `${search}ms`);
    document.body.style.setProperty('--sg-motion-delay-step', `${delayStep}ms`);
    document.body.style.setProperty('--sg-motion-background', `${bg}s`);
    document.body.style.setProperty('--sg-motion-halo', `${halo}s`);
  }
}

function refreshRankingView() {
  if (selectors.rankingPopularity) {
    selectors.rankingPopularity.value = String(preferences.ranking.popularity);
  }
  if (selectors.rankingHome) {
    selectors.rankingHome.value = String(preferences.ranking.home);
  }
  if (selectors.rankingPopularityValue) {
    selectors.rankingPopularityValue.textContent = `${formatWeight(preferences.ranking.popularity)}`;
  }
  if (selectors.rankingHomeValue) {
    selectors.rankingHomeValue.textContent = `${formatWeight(preferences.ranking.home)}`;
  }
}

function refreshMotionView() {
  if (selectors.motionForeground) {
    selectors.motionForeground.value = String(preferences.motion.foreground);
  }
  if (selectors.motionBackground) {
    selectors.motionBackground.value = String(preferences.motion.background);
  }
  if (selectors.motionForegroundValue) {
    selectors.motionForegroundValue.textContent = `${Math.round(preferences.motion.foreground)} ms`;
  }
  if (selectors.motionBackgroundValue) {
    selectors.motionBackgroundValue.textContent = `${Math.round(preferences.motion.background)} s`;
  }
  applyMotionPreferences();
}

function refreshSettingsView() {
  refreshRankingView();
  refreshMotionView();
}

function activateSettingsTab(tabName) {
  const activeName = tabName || 'general';
  settingsTabs.forEach((button) => {
    const isActive = button.dataset.tab === activeName;
    button.classList.toggle('is-active', isActive);
    button.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });
  settingsPanels.forEach((panel) => {
    const isActive = panel.dataset.tab === activeName;
    panel.classList.toggle('is-active', isActive);
    panel.hidden = !isActive;
  });
}

function openSettings(tabName = 'motion') {
  if (!selectors.settingsOverlay) {
    return;
  }
  settingsOpen = true;
  lastFocusedElement = document.activeElement;
  selectors.settingsOverlay.hidden = false;
  refreshSettingsView();
  activateSettingsTab(tabName);
  window.setTimeout(() => {
    const target = settingsTabs.find((button) => button.dataset.tab === tabName) || settingsTabs[0];
    if (target) {
      target.focus();
    }
  }, 0);
}

function closeSettings() {
  if (!selectors.settingsOverlay) {
    return;
  }
  selectors.settingsOverlay.hidden = true;
  settingsOpen = false;
  if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
    lastFocusedElement.focus();
  }
  lastFocusedElement = null;
}

function handleRankingChange(event) {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) {
    return;
  }
  const value = Number(target.value);
  if (Number.isNaN(value)) {
    return;
  }
  if (target === selectors.rankingPopularity) {
    preferences.ranking.popularity = value;
  } else if (target === selectors.rankingHome) {
    preferences.ranking.home = value;
  }
  refreshRankingView();
  savePreferences();
  rerenderSuggestions();
}

function handleMotionChange(event) {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) {
    return;
  }
  const value = Number(target.value);
  if (Number.isNaN(value)) {
    return;
  }
  if (target === selectors.motionForeground) {
    preferences.motion.foreground = value;
  } else if (target === selectors.motionBackground) {
    preferences.motion.background = value;
  }
  refreshMotionView();
  savePreferences();
  rerenderSuggestions();
}

function handleGlobalKeydown(event) {
  if (event.key === 'Escape' && settingsOpen) {
    event.preventDefault();
    closeSettings();
  }
}

function debounce(fn, delay) {
  let timer = null;
  function debounced(...args) {
    if (timer) {
      window.clearTimeout(timer);
    }
    timer = window.setTimeout(() => {
      timer = null;
      fn.apply(this, args);
    }, delay);
  }
  debounced.cancel = () => {
    if (timer) {
      window.clearTimeout(timer);
      timer = null;
    }
  };
  return debounced;
}

function renderSuggestions(items) {
  if (!selectors.suggestions) {
    return;
  }
  isRendering = true;
  try {
    setStage('searching');
    selectors.suggestions.innerHTML = '';
    if (selectors.error) {
      selectors.error.hidden = true;
    }
    lastSuggestions = Array.isArray(items) ? items.slice() : [];
    if (!items || !items.length) {
      if (selectors.empty) {
        selectors.empty.hidden = false;
      }
      return;
    }
    if (selectors.empty) {
      selectors.empty.hidden = true;
    }
    const rankedItems = rankSuggestions(items).slice(0, SEARCH_LIMIT);
    const delayStep = Math.max(10, Math.round(preferences.motion.foreground / 8));
    rankedItems.forEach((item, index) => {
      const entry = document.createElement('li');
      entry.className = 'suggestion-item';
      entry.style.animationDelay = `${index * delayStep}ms`;
      entry.setAttribute('tabindex', '0');
      const value = item.value || '';
      const labelText = item.label || value;
      const typeText = (item.type || 'object').toLowerCase();
      const addresses = Array.isArray(item.addresses) ? item.addresses : [];
      const primaryAddress = addresses.length ? addresses[0] : '';
      const contextText = item.context || item.config || '';
      const homeState = item.home || '';

      entry.dataset.value = value;
      entry.dataset.label = labelText;
      entry.dataset.type = typeText;
      entry.dataset.vendor = item.vendor || '';
      entry.dataset.config = item.config || '';
      entry.dataset.os = item.os || '';
      entry.dataset.version = item.version || '';
      entry.dataset.context = contextText;
      entry.dataset.addresses = JSON.stringify(addresses);
      entry.dataset.selectionKey = [typeText, entry.dataset.vendor, entry.dataset.config, value].join('::');
      entry.dataset.home = homeState;
      if (typeof item.score === 'number') {
        entry.dataset.score = String(item.score);
      }
      if (typeof item.popularity === 'number') {
        entry.dataset.popularity = String(item.popularity);
      }

      const main = document.createElement('div');
      main.className = 'suggestion-main';

      const name = document.createElement('span');
      name.className = 'suggestion-name';
      name.textContent = labelText;

      const tag = document.createElement('span');
      tag.className = 'suggestion-tag';
      tag.dataset.kind = typeText;
      tag.textContent = describeType(typeText).toUpperCase();

      main.appendChild(name);
      main.appendChild(tag);

      if (primaryAddress) {
        const address = document.createElement('span');
        address.className = 'suggestion-address';
        address.textContent = primaryAddress;
        main.appendChild(address);
      }

      const meta = document.createElement('div');
      meta.className = 'suggestion-meta';
      const context = document.createElement('span');
      context.className = 'suggestion-context';
      context.textContent = contextText;
      meta.appendChild(context);
      if (homeState) {
        const home = document.createElement('span');
        home.className = 'suggestion-home';
        home.dataset.kind = homeState;
        home.textContent = homeState === 'home' ? 'Home' : homeState === 'probable' ? 'Probable home' : homeState;
        meta.appendChild(home);
      }

      entry.appendChild(main);
      entry.appendChild(meta);

      entry.addEventListener('click', () => selectSuggestion(entry));
      entry.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          selectSuggestion(entry);
        }
      });

      selectors.suggestions.appendChild(entry);
    });
  } finally {
    isRendering = false;
  }
}

function buildUrl(base, params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null) {
      return;
    }
    const text = String(value);
    if (!text) {
      return;
    }
    search.set(key, text);
  });
  const query = search.toString();
  return query ? `${base}?${query}` : base;
}

function toggleActionVisibility(action, visible) {
  document.querySelectorAll(`[data-action="${action}"]`).forEach((anchor) => {
    anchor.classList.toggle('is-hidden', !visible);
    if (!visible) {
      anchor.removeAttribute('href');
    }
  });
}

function wireActionLinks(selection) {
  if (!selection) {
    toggleActionVisibility('inspect', false);
    toggleActionVisibility('compare', false);
    toggleActionVisibility('packet', false);
    toggleActionVisibility('find', false);
    return;
  }
  const vendor = selection.vendor || '';
  const config = selection.config || '';
  const value = selection.value || '';
  const hasScope = Boolean(vendor && config);
  const isContext = selection.type === 'context';
  const isObjectLike = !isContext && Boolean(value);

  const inspectParams = {
    tab: isContext ? 'config' : 'rules',
    vendor,
    config,
  };
  if (isObjectLike) {
    inspectParams.mode = 'inspect';
    inspectParams.inspect = value;
  }
  const compareParams = isObjectLike
    ? { tab: 'rules', mode: 'compare', vendor, config, old: value }
    : null;
  const packetParams = isObjectLike
    ? { tab: 'packet', vendor, config, pkt_src: value }
    : null;
  const findParams = {
    tab: 'find',
    vendor,
    config,
  };
  if (isObjectLike) {
    findParams.find = value;
  }

  document.querySelectorAll('[data-action="inspect"]').forEach((anchor) => {
    anchor.textContent = isContext ? 'Open configuration' : 'Inspect this object';
    if (hasScope) {
      anchor.href = buildUrl('/', inspectParams);
    } else {
      anchor.removeAttribute('href');
    }
  });

  toggleActionVisibility('inspect', hasScope);
  toggleActionVisibility('compare', hasScope && Boolean(compareParams));
  toggleActionVisibility('packet', hasScope && Boolean(packetParams));
  toggleActionVisibility('find', hasScope);

  if (compareParams) {
    document.querySelectorAll('[data-action="compare"]').forEach((anchor) => {
      anchor.href = buildUrl('/', compareParams);
    });
  }
  if (packetParams) {
    document.querySelectorAll('[data-action="packet"]').forEach((anchor) => {
      anchor.href = buildUrl('/', packetParams);
    });
  }
  if (hasScope) {
    document.querySelectorAll('[data-action="find"]').forEach((anchor) => {
      anchor.textContent = isContext ? 'Search inside this config' : 'Search across configs';
      anchor.href = buildUrl('/', findParams);
    });
  } else {
    document.querySelectorAll('[data-action="find"]').forEach((anchor) => {
      anchor.textContent = 'Search across configs';
      anchor.removeAttribute('href');
    });
  }
}

function collapseSuggestions(selectedElement, selectionKey) {
  if (!selectors.suggestions || !selectedElement) {
    return;
  }
  const items = Array.from(selectors.suggestions.children);
  items.forEach((node) => {
    if (node === selectedElement) {
      node.classList.add('is-selected');
    } else {
      node.classList.add('is-fading');
    }
  });
  const collapseDelay = Math.max(200, Math.round(preferences.motion.foreground + 120));
  window.setTimeout(() => {
    if (activeSelection !== selectionKey) {
      return;
    }
    if (selectors.suggestions) {
      selectors.suggestions.innerHTML = '';
    }
    if (selectors.empty) {
      selectors.empty.hidden = true;
    }
    setSuggestionState('idle');
    setStage('selected');
    lastSuggestions = [];
  }, collapseDelay);
}

async function fetchMeta(selection) {
  if (!selection || !selection.vendor || !selection.config) {
    return null;
  }
  const key = `${selection.vendor}:${selection.config}`;
  if (cache.meta.has(key)) {
    return cache.meta.get(key);
  }
  const promise = (async () => {
    try {
      const response = await fetch(
        buildUrl('/api/meta', {
          vendor: selection.vendor,
          config: selection.config,
        })
      );
      if (!response.ok) {
        return null;
      }
      return await response.json();
    } catch (err) {
      return null;
    }
  })();
  cache.meta.set(key, promise);
  return promise;
}

function describeSelectionMeta(selection, metaPayload) {
  const fragments = [];
  if (selection && selection.context) {
    fragments.push(selection.context);
  }
  if (metaPayload && metaPayload.os) {
    const version = metaPayload.version && metaPayload.version !== 'unknown' ? ` · ${metaPayload.version}` : '';
    fragments.push(`${metaPayload.os}${version}`);
  } else if (selection && selection.os) {
    fragments.push(selection.os);
  }
  if (!fragments.length) {
    return 'No additional context available.';
  }
  return fragments.join(' — ');
}

async function selectSuggestion(element) {
  const value = element.dataset.value || '';
  const type = element.dataset.type || 'object';
  const vendor = element.dataset.vendor || '';
  const config = element.dataset.config || '';
  const context = element.dataset.context || config;
  const selectionKey = element.dataset.selectionKey || `${type}::${vendor}::${config}::${value}`;
  if (!value && type !== 'context') {
    return;
  }
  const homeState = element.dataset.home || '';
  const popularityValue = Number(element.dataset.popularity || '0');
  let addresses = [];
  try {
    addresses = JSON.parse(element.dataset.addresses || '[]');
  } catch (err) {
    addresses = [];
  }
  const selection = {
    key: selectionKey,
    value,
    label: element.dataset.label || value || context,
    type,
    vendor,
    config,
    context,
    addresses,
    os: element.dataset.os || '',
    version: element.dataset.version || 'auto',
    home: homeState,
    popularity: popularityValue,
  };
  state.selection = selection;
  activeSelection = selectionKey;
  const displayValue =
    selection.type === 'context'
      ? selection.context
      : [selection.value, selection.addresses[0]].filter(Boolean).join(' ');
  if (selectors.query) {
    selectors.query.value = displayValue.trim();
    updateQueryResetVisibility(Boolean(selectors.query.value.length));
  }
  wireActionLinks(selection);
  collapseSuggestions(element, selectionKey);
  if (selectors.details) {
    selectors.details.hidden = false;
    selectors.details.classList.add('is-visible');
  }
  if (selectors.label) {
    selectors.label.textContent = selection.label;
  }
  if (selectors.type) {
    selectors.type.textContent = describeType(selection.type);
  }
  if (selectors.meta) {
    selectors.meta.textContent = 'Gathering device context…';
  }
  if (selectors.copy) {
    selectors.copy.disabled = false;
    selectors.copy.dataset.value = (displayValue && displayValue.trim()) || selection.label;
  }

  const metaPayload = await fetchMeta(selection);
  if (activeSelection !== selectionKey) {
    return;
  }
  if (selectors.meta) {
    selectors.meta.textContent = describeSelectionMeta(selection, metaPayload);
  }
}

async function requestSuggestions(query) {
  const trimmed = (query || '').trim();
  state.lastQuery = trimmed;
  if (!trimmed) {
    clearSuggestions();
    hideDetails();
    return;
  }
  const token = ++activeFetchToken;
  setStage('searching');
  setSuggestionState('loading');
  try {
    const response = await fetch(
      buildUrl('/api/objects', {
        vendor: 'all',
        version: 'auto',
        q: trimmed,
        mode: state.mode,
        limit: String(SEARCH_LIMIT),
      })
    );
    if (token !== activeFetchToken) {
      return;
    }
    if (!response.ok) {
      if (selectors.error) {
        selectors.error.hidden = false;
        selectors.error.textContent = 'Suggestion service is unavailable right now.';
      }
      setSuggestionState('idle');
      return;
    }
    const payload = await response.json();
    setSuggestionState('idle');
    renderSuggestions(payload.items || []);
  } catch (err) {
    if (token !== activeFetchToken) {
      return;
    }
    if (selectors.error) {
      selectors.error.hidden = false;
      selectors.error.textContent = 'Network hiccup. Try again in a moment.';
    }
    setSuggestionState('idle');
  }
}

const debouncedRequest = debounce(requestSuggestions, 180);

function handleQueryInput(event) {
  if (selectors.error) {
    selectors.error.hidden = true;
  }
  const value = event.target.value || '';
  updateQueryResetVisibility(Boolean(value.trim().length));
  if (state.selection) {
    hideDetails();
  }
  if (!value.trim()) {
    setStage('idle');
  } else {
    setStage('searching');
  }
  debouncedRequest(value);
}

function handleCopy() {
  const value = selectors.copy && selectors.copy.dataset.value;
  if (!value) {
    return;
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(value).catch(() => {});
  }
}

function toggleAdvanced(explicit) {
  if (!selectors.advanced || !selectors.reveal) {
    return;
  }
  const isOpen =
    typeof explicit === 'boolean' ? explicit : selectors.reveal.getAttribute('aria-expanded') === 'true';
  const next = !isOpen;
  selectors.reveal.setAttribute('aria-expanded', String(next));
  selectors.advanced.hidden = !next;
}

function initEvents() {
  if (selectors.query) {
    selectors.query.addEventListener('input', handleQueryInput);
    selectors.query.addEventListener('focus', () => {
      if (selectors.hint) {
        selectors.hint.textContent = '';
      }
    });
  }
  if (selectors.queryReset) {
    selectors.queryReset.addEventListener('click', clearQuery);
  }
  if (selectors.copy) {
    selectors.copy.addEventListener('click', handleCopy);
  }
  if (selectors.reveal) {
    selectors.reveal.addEventListener('click', () => toggleAdvanced());
  }
  if (selectors.settingsToggle) {
    selectors.settingsToggle.addEventListener('click', () => openSettings('motion'));
  }
  if (selectors.settingsOverlay) {
    selectors.settingsOverlay.addEventListener('click', (event) => {
      if (event.target === selectors.settingsOverlay) {
        closeSettings();
      }
    });
  }
  if (selectors.settingsClose) {
    selectors.settingsClose.addEventListener('click', () => closeSettings());
  }
  settingsTabs.forEach((button) => {
    button.addEventListener('click', () => activateSettingsTab(button.dataset.tab || 'general'));
  });
  if (selectors.rankingPopularity) {
    selectors.rankingPopularity.addEventListener('input', handleRankingChange);
  }
  if (selectors.rankingHome) {
    selectors.rankingHome.addEventListener('input', handleRankingChange);
  }
  if (selectors.motionForeground) {
    selectors.motionForeground.addEventListener('input', handleMotionChange);
  }
  if (selectors.motionBackground) {
    selectors.motionBackground.addEventListener('input', handleMotionChange);
  }
  updateQueryResetVisibility(Boolean(selectors.query && selectors.query.value && selectors.query.value.trim().length));
  document.addEventListener('keydown', handleGlobalKeydown);
}

function init() {
  setStage('idle');
  initThemeControls();
  initEvents();
  if (selectors.hint) {
    selectors.hint.textContent = '';
  }
  if (selectors.copy) {
    selectors.copy.disabled = true;
  }
  refreshSettingsView();
  activateSettingsTab('general');
}

init();
