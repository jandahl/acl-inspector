const DATA = window.SINGULARITY_DATA || {};

const state = {
  vendor: (DATA.defaultVendor || 'asa').toLowerCase(),
  config: DATA.defaultConfig || '',
  mode: (DATA.defaultMode || 'fuzzy').toLowerCase(),
};

const cache = {
  meta: new Map(),
};

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
  vendor: document.querySelector('[data-role="vendor"]'),
  config: document.querySelector('[data-role="config"]'),
  mode: document.querySelector('[data-role="mode"]'),
  configChip: document.querySelector('[data-role="config-chip"]'),
  scopeToggle: document.querySelector('[data-role="toggle-advanced"]'),
  scopePanel: document.querySelector('[data-role="scope-panel"]'),
};

if (selectors.vendor && state.vendor !== selectors.vendor.value) {
  selectors.vendor.value = state.vendor;
}

const SEARCH_LIMIT = Number(DATA.searchLimit || 12) || 12;
const configOptions = DATA.configOptions || { asa: [], fortigate: [] };
let activeFetchToken = 0;
let activeSelection = null;

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

function pickDefaultConfig() {
  if (state.config) {
    return;
  }
  const options = configOptions[state.vendor] || [];
  state.config = options.length > 0 ? options[0] : '';
}

function updateConfigChip() {
  if (!selectors.configChip) {
    return;
  }
  if (!state.config) {
    selectors.configChip.textContent = 'No config selected';
    selectors.configChip.classList.add('is-empty');
  } else {
    selectors.configChip.textContent = state.config;
    selectors.configChip.classList.remove('is-empty');
  }
}

function populateConfigSelect() {
  if (!selectors.config) {
    return;
  }
  const options = configOptions[state.vendor] || [];
  selectors.config.innerHTML = '';
  for (const name of options) {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    if (name === state.config) {
      option.selected = true;
    }
    selectors.config.appendChild(option);
  }
  if (!state.config && options.length) {
    state.config = options[0];
  }
  selectors.config.disabled = options.length === 0;
  updateConfigChip();
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
    entry.dataset.value = item.value;
    entry.dataset.label = item.label || item.value;
    entry.dataset.type = item.type || 'object';

    const label = document.createElement('div');
    label.className = 'suggestion-label';
    label.textContent = item.label || item.value;

    const type = document.createElement('div');
    type.className = 'suggestion-type';
    type.textContent = describeType(item.type);

    entry.appendChild(label);
    entry.appendChild(type);

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

function wireActionLinks(value) {
  const shared = {
    vendor: state.vendor,
    config: state.config || '',
  };
  const inspectUrl = buildUrl('/', {
    tab: 'rules',
    mode: 'inspect',
    vendor: shared.vendor,
    config: shared.config,
    inspect: value,
  });
  const compareUrl = buildUrl('/', {
    tab: 'rules',
    mode: 'compare',
    vendor: shared.vendor,
    config: shared.config,
    old: value,
  });
  const packetUrl = buildUrl('/', {
    tab: 'packet',
    vendor: shared.vendor,
    config: shared.config,
    pkt_src: value,
  });
  const findUrl = buildUrl('/', {
    tab: 'find',
    vendor: shared.vendor,
    config: shared.config,
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

async function fetchMeta() {
  const key = `${state.vendor}:${state.config}`;
  if (!state.config) {
    return null;
  }
  if (cache.meta.has(key)) {
    return cache.meta.get(key);
  }
  const promise = (async () => {
    try {
      const response = await fetch(
        buildUrl('/api/meta', {
          vendor: state.vendor,
          config: state.config,
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

function describeSelectionMeta(metaPayload) {
  const fragments = [];
  if (state.config) {
    fragments.push(`From ${state.config}`);
  }
  if (metaPayload && metaPayload.os) {
    const version = metaPayload.version && metaPayload.version !== 'unknown' ? ` · ${metaPayload.version}` : '';
    fragments.push(`${metaPayload.os}${version}`);
  }
  if (!fragments.length) {
    return 'Scope not configured yet.';
  }
  return fragments.join(' — ');
}

async function selectSuggestion(element) {
  const value = element.dataset.value || '';
  if (!value) {
    return;
  }
  toggleScopePanel(false);
  activeSelection = value;
  wireActionLinks(value);
  if (selectors.details) {
    selectors.details.hidden = false;
    selectors.details.classList.add('is-visible');
  }
  if (selectors.label) {
    selectors.label.textContent = element.dataset.label || value;
  }
  if (selectors.type) {
    selectors.type.textContent = describeType(element.dataset.type);
  }
  if (selectors.meta) {
    selectors.meta.textContent = 'Gathering device context…';
  }
  if (selectors.copy) {
    selectors.copy.disabled = false;
    selectors.copy.dataset.value = value;
  }

  const metaPayload = await fetchMeta();
  if (activeSelection !== value) {
    return;
  }
  if (selectors.meta) {
    selectors.meta.textContent = describeSelectionMeta(metaPayload);
  }
}

async function requestSuggestions(query) {
  const trimmed = (query || '').trim();
  if (!trimmed) {
    clearSuggestions();
    hideDetails();
    return;
  }
  if (!state.config) {
    clearSuggestions();
    if (selectors.error) {
      selectors.error.hidden = false;
      selectors.error.textContent = 'Select a configuration to search.';
    }
    hideDetails();
    toggleScopePanel(true);
    return;
  }
  const token = ++activeFetchToken;
  setSuggestionState('loading');
  try {
    const response = await fetch(
      buildUrl('/api/objects', {
        vendor: state.vendor,
        os: state.vendor.toUpperCase(),
        version: 'auto',
        config: state.config,
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

function toggleScopePanel(force) {
  if (!selectors.scopePanel || !selectors.scopeToggle) {
    return;
  }
  const current = selectors.scopeToggle.getAttribute('aria-expanded') === 'true';
  const next = typeof force === 'boolean' ? force : !current;
  selectors.scopeToggle.setAttribute('aria-expanded', String(next));
  selectors.scopePanel.hidden = !next;
  if (next && typeof selectors.scopePanel.scrollIntoView === 'function') {
    const prefersReduced =
      typeof window !== 'undefined' && window.matchMedia
        ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
        : false;
    try {
      selectors.scopePanel.scrollIntoView({ behavior: prefersReduced ? 'auto' : 'smooth', block: 'start' });
    } catch (err) {
      selectors.scopePanel.scrollIntoView();
    }
  }
}

function initEvents() {
  if (selectors.query) {
    selectors.query.addEventListener('input', handleQueryInput);
    selectors.query.addEventListener('focus', () => {
      if (selectors.hint) {
        selectors.hint.textContent = 'Try a host, network, or object name. We will suggest the rest.';
      }
    });
  }
  if (selectors.copy) {
    selectors.copy.addEventListener('click', handleCopy);
  }
  if (selectors.reveal) {
    selectors.reveal.addEventListener('click', () => toggleAdvanced());
  }
  if (selectors.scopeToggle) {
    selectors.scopeToggle.addEventListener('click', () => toggleScopePanel());
  }
  if (selectors.vendor) {
    selectors.vendor.addEventListener('change', (event) => {
      state.vendor = event.target.value || 'asa';
      state.config = '';
      pickDefaultConfig();
      populateConfigSelect();
      clearSuggestions();
      cache.meta.clear();
      hideDetails();
    });
  }
  if (selectors.config) {
    selectors.config.addEventListener('change', (event) => {
      state.config = event.target.value || '';
      updateConfigChip();
      clearSuggestions();
      cache.meta.clear();
      hideDetails();
    });
  }
  if (selectors.mode) {
    selectors.mode.value = state.mode;
    selectors.mode.addEventListener('change', (event) => {
      state.mode = event.target.value || 'fuzzy';
      if (selectors.query && selectors.query.value) {
        debouncedRequest(selectors.query.value);
      }
    });
  }
}

function init() {
  pickDefaultConfig();
  populateConfigSelect();
  updateConfigChip();
  initEvents();
  if (selectors.hint) {
    selectors.hint.textContent = DATA.initialHint || 'Start typing to explore suggestions across your configs.';
  }
  if (selectors.copy) {
    selectors.copy.disabled = true;
  }
  if (!state.config) {
    toggleScopePanel(true);
    if (selectors.hint) {
      selectors.hint.textContent = 'Add a config under Scope before searching.';
    }
  }
}

init();
