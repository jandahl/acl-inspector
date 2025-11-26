SHELL := /bin/bash
WEB_PORT ?= 8083
THEMES_REPO ?= https://github.com/mbadolato/iTerm2-Color-Schemes.git
THEMES_DIR ?= themes

# Prefer the project virtualenv if it exists
VENV_DIR ?= .venv
VENV_BIN := $(VENV_DIR)/bin
ifneq ($(wildcard $(VENV_BIN)/python),)
PYTHON ?= $(VENV_BIN)/python
else
PYTHON ?= python3
endif

.PHONY: help venv lint test unit examples tui web web-watch build clean themes themes-refresh fonts

help:
	@echo "Targets:"
	@echo "  venv      - create .venv and upgrade pip"
	@echo "  lint      - run optional linters if installed"
	@echo "  unit      - run python -m unittest"
	@echo "  test      - run self-test via CLI"
	@echo "  examples  - print CLI examples"
	@echo "  tui       - launch the terminal UI"
	@echo "  web       - run the web UI (localhost:$(WEB_PORT))"
	@echo "             (override config dirs: make web CONFIGS_CISCO=/path/to/asa CONFIGS_FORTIGATE=/path/to/ftg)"
	@echo "  web-e2e   - run Playwright-based UI smoke tests"
	@echo "  web-watch - run the web UI with an auto-reloader (requires Python 3.9+)"
	@echo "  fonts     - download libre fonts into fonts/downloaded/ (set FORCE=1 to refresh)"
	@echo "  container-build - build the web UI container image"
	@echo "  container-run   - run the web UI container (localhost:8083)"
	@echo "  container-status- show the status of the web UI container"
	@echo "  container-logs  - show logs of the web UI container"
	@echo "  container-stop  - stop the web UI container"
	@echo "  container-prune - stop and remove the container, but keep the built image"
	@echo "  container-clean - stop and remove the web UI container"
	@echo "  index     - index a repo root into cache (set ROOT=/path CACHE=./cache)"
	@echo "  build     - compile key Python modules"
	@echo "  clean     - remove __pycache__/ and .pyc_cache"

venv:
	./scripts/setup_venv.sh

lint:
	@command -v ruff >/dev/null 2>&1 && ruff check . || echo "ruff not installed; skipping"
	@command -v flake8 >/dev/null 2>&1 && flake8 || echo "flake8 not installed; skipping"

unit:
	$(PYTHON) -m unittest discover -s tests -v

test:
	PYTHONPYCACHEPREFIX=.pyc_cache $(PYTHON) aclinspector.py inspect --self-test

test-minimal:
	@PYTHONPYCACHEPREFIX=.pyc_cache $(PYTHON) aclinspector.py inspect --self-test 2>&1 | awk 'NF==0 || /^(PYTHONPYCACHEPREFIX|FAILED|ERROR|Ran|OK|Skipped)/'

examples:
	$(PYTHON) aclinspector.py inspect --examples

tui:
	$(if $(CONFIGS_CISCO),ACLINSPECTOR_CONFIGS_CISCO=$(CONFIGS_CISCO) ,)\
	$(if $(CONFIGS_FORTIGATE),ACLINSPECTOR_CONFIGS_FORTIGATE=$(CONFIGS_FORTIGATE) ,)\
	$(if $(ACLINSPECTOR_PREWARM_ALL),ACLINSPECTOR_PREWARM_ALL=$(ACLINSPECTOR_PREWARM_ALL) ,)\
	PYTHONPYCACHEPREFIX=.pyc_cache $(PYTHON) aclinspector.py tui $(ARGS)

web:
	$(if $(CONFIGS_CISCO),ACLINSPECTOR_CONFIGS_CISCO=$(CONFIGS_CISCO) ,)\
	$(if $(CONFIGS_FORTIGATE),ACLINSPECTOR_CONFIGS_FORTIGATE=$(CONFIGS_FORTIGATE) ,)\
	$(PYTHON) aclinspector.py web --port $(WEB_PORT)

web-watch:
	PYTHONPYCACHEPREFIX=.pyc_cache $(PYTHON) scripts/web_autoreload.py --port $(WEB_PORT) \
		$(if $(CONFIGS_CISCO),--configs-cisco $(CONFIGS_CISCO),) \
		$(if $(CONFIGS_FORTIGATE),--configs-fortigate $(CONFIGS_FORTIGATE),) \
		$(if $(POLL),--poll $(POLL),)

web-e2e:
	PYTHONPYCACHEPREFIX=.pyc_cache $(PYTHON) -m unittest tests.test_ui_playwright

themes:
	@mkdir -p $(THEMES_DIR)
	@if [ ! -f $(THEMES_DIR)/.source ]; then \
		tmp=$$(mktemp -d); \
		git clone --depth 1 $(THEMES_REPO) $$tmp/iterm >/dev/null 2>&1; \
		cp -f $$tmp/iterm/schemes/*.itermcolors $(THEMES_DIR)/ 2>/dev/null || true; \
		cp -f $$tmp/iterm/schemes/*.yaml $(THEMES_DIR)/ 2>/dev/null || true; \
		echo "$(THEMES_REPO)" > $(THEMES_DIR)/.source; \
		rm -rf $$tmp; \
	fi

themes-refresh:
	rm -f $(THEMES_DIR)/.source
	$(MAKE) themes

fonts:
	@$(PYTHON) scripts/download_fonts.py $(if $(FORCE),--force,)

# Container targets
CONTAINER_COMPOSE :=
CONTAINER_HEALTH_CHECK := true
ifeq ($(shell command -v docker-compose 2>/dev/null),)
ifeq ($(shell command -v podman-compose 2>/dev/null),)
$(error "Neither docker-compose nor podman-compose found. Please install one to use container targets.")
else
CONTAINER_COMPOSE := podman-compose
CONTAINER_HEALTH_CHECK := \
	if ! podman info >/dev/null 2>&1; then \
		echo "Podman daemon is not reachable."; \
		echo "Run 'podman machine start' (macOS) or ensure 'podman system service' is active, then retry."; \
		exit 1; \
	fi;
endif
else
CONTAINER_COMPOSE := docker-compose
CONTAINER_HEALTH_CHECK := \
	if ! docker info >/dev/null 2>&1; then \
		echo "Docker daemon is not reachable."; \
		echo "Start Docker Desktop or your docker service, then retry."; \
		exit 1; \
	fi;
endif


container-build:
	@echo "Using $(CONTAINER_COMPOSE) to build the container image..."
	@$(CONTAINER_HEALTH_CHECK)
	$(if $(CONFIGS_CISCO),ACLINSPECTOR_CONFIGS_CISCO=$(CONFIGS_CISCO) ,)\
	$(if $(CONFIGS_FORTIGATE),ACLINSPECTOR_CONFIGS_FORTIGATE=$(CONFIGS_FORTIGATE) ,)\
	$(CONTAINER_COMPOSE) -f Dockersetup/podman-compose.yaml -p aclinspector up --build -d --no-start

container-run:
	@echo "Using $(CONTAINER_COMPOSE) to run the container..."
	@$(CONTAINER_HEALTH_CHECK)
	$(if $(CONFIGS_CISCO),ACLINSPECTOR_CONFIGS_CISCO=$(CONFIGS_CISCO) ,)\
	$(if $(CONFIGS_FORTIGATE),ACLINSPECTOR_CONFIGS_FORTIGATE=$(CONFIGS_FORTIGATE) ,)\
	$(CONTAINER_COMPOSE) -f Dockersetup/podman-compose.yaml -p aclinspector up -d
	@echo "\nWeb UI is now running. Connect to http://localhost:8083"

container-status:
	@echo "Using $(CONTAINER_COMPOSE) to show container status..."
	@$(CONTAINER_HEALTH_CHECK)
	$(CONTAINER_COMPOSE) -f Dockersetup/podman-compose.yaml -p aclinspector ps

container-logs:
	@echo "Using $(CONTAINER_COMPOSE) to show container logs (tail -f)..."
	@$(CONTAINER_HEALTH_CHECK)
	$(CONTAINER_COMPOSE) -f Dockersetup/podman-compose.yaml -p aclinspector logs -f acl-inspector-web

container-stop:
	@echo "Using $(CONTAINER_COMPOSE) to stop the container..."
	@$(CONTAINER_HEALTH_CHECK)
	$(CONTAINER_COMPOSE) -f Dockersetup/podman-compose.yaml -p aclinspector stop

container-prune:
	@echo "Using $(CONTAINER_COMPOSE) to remove the container while keeping cached images..."
	@$(CONTAINER_HEALTH_CHECK)
	$(CONTAINER_COMPOSE) -f Dockersetup/podman-compose.yaml -p aclinspector down

container-clean:
	@echo "Using $(CONTAINER_COMPOSE) to stop and remove the container..."
	@$(CONTAINER_HEALTH_CHECK)
	$(CONTAINER_COMPOSE) -f Dockersetup/podman-compose.yaml -p aclinspector down --rmi all --volumes

build: themes fonts
PYTHONPYCACHEPREFIX=.pyc_cache $(PYTHON) -m py_compile cli/access-list-inspector.py parsers/cisco/asa.py parsers/fortigate/fortigate.py cli/access-list-web.py

clean:
	rm -rf __pycache__ */__pycache__ .pyc_cache

index:
	@if [ -z "$(ROOT)" ]; then echo "Usage: make index ROOT=/path/to/repo CACHE=./cache"; exit 1; fi
	@mkdir -p $(CACHE)
	$(PYTHON) scripts/index_repo.py --root $(ROOT) --cache-dir $(CACHE)
