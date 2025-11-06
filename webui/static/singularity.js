const DATA = window.SINGULARITY_DATA || {};

const state = {
  mode: (DATA.defaultMode || 'fuzzy').toLowerCase(),
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
};

const SEARCH_LIMIT = Number(DATA.searchLimit || 12) || 12;
let activeFetchToken = 0;
let activeSelection = null;

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
  if (selectors.empty) {
    selectors.empty.hidden = false;
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
    default:
      return 'Object';
  }
}

function debounce(fn, delay) {
  let timer = null;
  return function debounced(...args) {
    if (timer) {
      window.clearTimeout(timer);
    }
    timer = window.setTimeout(() => fn.apply(this, args), delay);
  };
}

function renderSuggestions(items) {
  if (!selectors.suggestions) {
    return;
  }
  selectors.suggestions.innerHTML = '';
  if (selectors.error) {
    selectors.error.hidden = true;
  }
  if (!items || !items.length) {
    if (selectors.empty) {
      selectors.empty.hidden = false;
    }
    return;
  }
  if (selectors.empty) {
    selectors.empty.hidden = true;
  }
  items.slice(0, SEARCH_LIMIT).forEach((item, index) => {
    const entry = document.createElement('li');
    entry.className = 'suggestion-item';
    entry.style.animationDelay = `${index * 25}ms`;
    entry.setAttribute('tabindex', '0');
    entry.dataset.value = item.value || '';
    entry.dataset.label = item.label || item.value || '';
    entry.dataset.type = item.type || 'object';
    entry.dataset.vendor = (item.vendor || '').toLowerCase();
    entry.dataset.config = item.config || '';
    entry.dataset.context = item.context || item.config || '';
    const primary = item.primary || (Array.isArray(item.literals) && item.literals.length ? item.literals[0] : '');
    entry.dataset.primary = primary || '';

    const main = document.createElement('div');
    main.className = 'suggestion-main';

    const title = document.createElement('div');
    title.className = 'suggestion-title';

    const name = document.createElement('span');
    name.className = 'suggestion-name';
    name.textContent = entry.dataset.label;

    const tag = document.createElement('span');
    tag.className = 'suggestion-tag';
    tag.textContent = `[ ${describeType(item.type).toUpperCase()} ]`;

    const ip = document.createElement('span');
    ip.className = 'suggestion-ip';
    if (primary) {
      ip.textContent = primary;
    } else {
      ip.classList.add('is-empty');
      ip.textContent = '';
    }

    title.appendChild(name);
    title.appendChild(tag);
    title.appendChild(ip);

    main.appendChild(title);

    const context = document.createElement('div');
    context.className = 'suggestion-context';
    context.textContent = entry.dataset.context;
    if (!context.textContent) {
      context.classList.add('is-empty');
    }

    entry.appendChild(main);
    entry.appendChild(context);

    entry.addEventListener('click', () => selectSuggestion(entry));
    entry.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectSuggestion(entry);
      }
    });

    selectors.suggestions.appendChild(entry);
  });
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

function wireActionLinks(value, vendor, config) {
  const sharedVendor = (vendor || '').toLowerCase();
  const sharedConfig = config || '';
  const inspectUrl = buildUrl('/', {
    tab: 'rules',
    mode: 'inspect',
    vendor: sharedVendor,
    config: sharedConfig,
    inspect: value,
  });
  const compareUrl = buildUrl('/', {
    tab: 'rules',
    mode: 'compare',
    vendor: sharedVendor,
    config: sharedConfig,
    old: value,
  });
  const packetUrl = buildUrl('/', {
    tab: 'packet',
    vendor: sharedVendor,
    config: sharedConfig,
    pkt_src: value,
  });
  const findUrl = buildUrl('/', {
    tab: 'find',
    vendor: sharedVendor,
    config: sharedConfig,
    find: value,
  });

  document.querySelectorAll('[data-action="inspect"]').forEach((anchor) => {
    anchor.href = inspectUrl;
  });
  document.querySelectorAll('[data-action="compare"]').forEach((anchor) => {
    anchor.href = compareUrl;
  });
  document.querySelectorAll('[data-action="packet"]').forEach((anchor) => {
    anchor.href = packetUrl;
  });
  document.querySelectorAll('[data-action="find"]').forEach((anchor) => {
    anchor.href = findUrl;
  });
}

async function fetchMeta(vendor, config) {
  const key = `${vendor}:${config}`;
  if (!vendor || !config) {
    return null;
  }
  if (cache.meta.has(key)) {
    return cache.meta.get(key);
  }
  const promise = (async () => {
    try {
      const response = await fetch(
        buildUrl('/api/meta', {
          vendor,
          config,
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
    fragments.push(`From ${selection.context}`);
  }
  if (metaPayload && metaPayload.os) {
    const version = metaPayload.version && metaPayload.version !== 'unknown' ? ` · ${metaPayload.version}` : '';
    fragments.push(`${metaPayload.os}${version}`);
  } else if (metaPayload && metaPayload.vendor) {
    fragments.push(metaPayload.vendor);
  }
  if (!fragments.length) {
    return 'Context will appear once the inspector opens.';
  }
  return fragments.join(' — ');
}

async function selectSuggestion(element) {
  const value = element.dataset.value || '';
  if (!value) {
    return;
  }
  const selection = {
    value,
    label: element.dataset.label || value,
    type: element.dataset.type || 'object',
    vendor: element.dataset.vendor || '',
    config: element.dataset.config || '',
    context: element.dataset.context || '',
    primary: element.dataset.primary || '',
  };
  selection.key = `${selection.vendor}:${selection.config}:${selection.value}`;
  activeSelection = selection;
  wireActionLinks(value, selection.vendor, selection.config);
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
    selectors.copy.dataset.value = value;
  }

  const metaPayload = await fetchMeta(selection.vendor, selection.config);
  if (!activeSelection || activeSelection.key !== selection.key) {
    return;
  }
  if (selectors.meta) {
    selectors.meta.textContent = describeSelectionMeta(selection, metaPayload);
  }
}

async function requestSuggestions(query) {
  const trimmed = (query || '').trim();
  if (!trimmed) {
    clearSuggestions();
    hideDetails();
    return;
  }
  const token = ++activeFetchToken;
  setSuggestionState('loading');
  try {
    const response = await fetch(
      buildUrl('/api/singularity/suggest', {
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
  debouncedRequest(event.target.value);
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
        selectors.hint.textContent = 'Try a host, network, or object name. Results span every config.';
      }
    });
  }
  if (selectors.copy) {
    selectors.copy.addEventListener('click', handleCopy);
  }
  if (selectors.reveal) {
    selectors.reveal.addEventListener('click', () => toggleAdvanced());
  }
}

function init() {
  initThemeControls();
  initEvents();
  if (selectors.hint) {
    selectors.hint.textContent = DATA.initialHint || 'Start typing to explore suggestions across your configs.';
  }
  if (selectors.copy) {
    selectors.copy.disabled = true;
  }
}

init();
