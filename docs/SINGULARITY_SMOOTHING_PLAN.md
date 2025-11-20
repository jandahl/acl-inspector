# Singularity UX Smoothing Plan (Planning Only)

This document captures the next set of improvements for the Singularity web
experience. No code has been written yet; the goal is to outline work that can
be executed incrementally once priorities are confirmed.

## 1. Perceived Performance

* **Preload bundle + critical data** – ship a lightweight `singularity-preload.js`
  that fetches config metadata (vendor list, search limit) as soon as the page
  loads to avoid the first keystroke penalty.
* **Cache last query** – persist the most recent search + results in
  `localStorage`, restoring it immediately on page load while the network call
  refreshes in the background.
* **Progress indicators** – add a tiny inline skeleton for the result rows so
  typing never leaves an empty pane.

## 2. Input / Results Workflow

* **Multi-column suggestion list** – show object name + config context + vendor
  column so the dropdown feels less noisy.
* **Keyboard affordances** – ensure arrow keys + `Enter` work even when the
  input loses focus. Consider a `Ctrl+K` launcher that focuses the search bar.
* **Inline filters** – expose protocol/port filters directly beneath the input
  instead of on the side to minimize mouse travel.

## 3. Visual Polish

* **Adaptive density** – detect viewport width and swap between the dense grid
  and a “card” layout for narrow laptops.
* **Theme tokens** – share the same design token system between TUI/Web/Singularity
  so switching modes feels consistent.
* **Error banner** – when an API call fails, show a non-blocking toast instead
  of replacing the entire results area.

## 4. Operational Improvements

* **Health endpoint** – add `/singularity/health` returning current cache/queue
  status so operations can monitor readiness.
* **Search telemetry** – capture anonymized stats (query length, result count,
  latency bucket) to guide future optimisation.
* **Docs & onboarding** – write a short “Singularity Quickstart” snippet in the
  README with gif/screenshots for new users.

Once we begin implementation we can break these into discrete issues (preload,
cache, keyboard UX, etc.) and track progress. For now this plan serves as the
backlog for smoothing the experience.***
