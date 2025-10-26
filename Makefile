SHELL := /bin/bash
WEB_PORT ?= 8083

.PHONY: help venv lint test unit examples web build clean

help:
	@echo "Targets:"
	@echo "  venv      - create .venv and upgrade pip"
	@echo "  lint      - run optional linters if installed"
	@echo "  unit      - run python -m unittest"
	@echo "  test      - run self-test via CLI"
	@echo "  examples  - print CLI examples"
	@echo "  web       - run the web UI (localhost:$(WEB_PORT))"
	@echo "             (override config dirs: make web CONFIGS_CISCO=/path/to/asa CONFIGS_FORTIGATE=/path/to/ftg)"
	@echo "  web-e2e   - run Playwright-based UI smoke tests"
	@echo "  container-build - build the web UI container image"
	@echo "  container-run   - run the web UI container (localhost:8083)"
	@echo "  container-status- show the status of the web UI container"
	@echo "  container-logs  - show logs of the web UI container"
	@echo "  container-stop  - stop the web UI container"
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
	python3 -m unittest discover -s tests -v

test:
	./access-list-inspector.py --self-test

examples:
	./access-list-inspector.py --examples

web:
	$(if $(CONFIGS_CISCO),ACLINSPECTOR_CONFIGS_CISCO=$(CONFIGS_CISCO) ,)\
	$(if $(CONFIGS_FORTIGATE),ACLINSPECTOR_CONFIGS_FORTIGATE=$(CONFIGS_FORTIGATE) ,)\
	./access-list-web.py --port $(WEB_PORT)

web-e2e:
	PYTHONPYCACHEPREFIX=.pyc_cache python3 -m unittest tests.test_ui_playwright

# Container targets
CONTAINER_COMPOSE :=
ifeq ($(shell command -v docker-compose 2>/dev/null),)
ifeq ($(shell command -v podman-compose 2>/dev/null),)
$(error "Neither docker-compose nor podman-compose found. Please install one to use container targets.")
else
CONTAINER_COMPOSE := podman-compose
endif
else
CONTAINER_COMPOSE := docker-compose
endif


container-build:
	@echo "Using $(CONTAINER_COMPOSE) to build the container image..."
	$(if $(CONFIGS_CISCO),ACLINSPECTOR_CONFIGS_CISCO=$(CONFIGS_CISCO) ,)\
	$(if $(CONFIGS_FORTIGATE),ACLINSPECTOR_CONFIGS_FORTIGATE=$(CONFIGS_FORTIGATE) ,)\
	$(CONTAINER_COMPOSE) -f Dockersetup/podman-compose.yaml -p aclinspector up --build -d --no-start

container-run:
	@echo "Using $(CONTAINER_COMPOSE) to run the container..."
	$(if $(CONFIGS_CISCO),ACLINSPECTOR_CONFIGS_CISCO=$(CONFIGS_CISCO) ,)\
	$(if $(CONFIGS_FORTIGATE),ACLINSPECTOR_CONFIGS_FORTIGATE=$(CONFIGS_FORTIGATE) ,)\
	$(CONTAINER_COMPOSE) -f Dockersetup/podman-compose.yaml -p aclinspector up -d
	@echo "\nWeb UI is now running. Connect to http://localhost:8083"

container-status:
	@echo "Using $(CONTAINER_COMPOSE) to show container status..."
	$(CONTAINER_COMPOSE) -f Dockersetup/podman-compose.yaml -p aclinspector ps

container-logs:
	@echo "Using $(CONTAINER_COMPOSE) to show container logs (tail -f)..."
	$(CONTAINER_COMPOSE) -f Dockersetup/podman-compose.yaml -p aclinspector logs -f acl-inspector-web

container-stop:
	@echo "Using $(CONTAINER_COMPOSE) to stop the container..."
	$(CONTAINER_COMPOSE) -f Dockersetup/podman-compose.yaml -p aclinspector stop

container-clean:
	@echo "Using $(CONTAINER_COMPOSE) to stop and remove the container..."
	$(CONTAINER_COMPOSE) -f Dockersetup/podman-compose.yaml -p aclinspector down --rmi all --volumes

build:
	PYTHONPYCACHEPREFIX=.pyc_cache python3 -m py_compile access-list-inspector.py parsers/cisco/asa.py parsers/fortigate/fortigate.py access-list-web.py

clean:
	rm -rf __pycache__ */__pycache__ .pyc_cache

index:
	@if [ -z "$(ROOT)" ]; then echo "Usage: make index ROOT=/path/to/repo CACHE=./cache"; exit 1; fi
	@mkdir -p $(CACHE)
	python3 scripts/index_repo.py --root $(ROOT) --cache-dir $(CACHE)
