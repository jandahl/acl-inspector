SHELL := /bin/bash

.PHONY: help venv lint test unit examples web build clean

help:
	@echo "Targets:"
	@echo "  venv      - create .venv and upgrade pip"
	@echo "  lint      - run optional linters if installed"
	@echo "  unit      - run python -m unittest"
	@echo "  test      - run self-test via CLI"
	@echo "  examples  - print CLI examples"
	@echo "  web       - run the web UI (localhost:8080)"
	@echo "  container-build - build the web UI container image"
	@echo "  container-run   - run the web UI container (localhost:8083)"
	@echo "  container-status- show the status of the web UI container"
	@echo "  container-stop  - stop the web UI container"
	@echo "  container-clean - stop and remove the web UI container"
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
	./access-list-web.py --port 8080

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
	cd Dockersetup && $(CONTAINER_COMPOSE) -p aclinspector up --build -d --no-start

container-run:
	@echo "Using $(CONTAINER_COMPOSE) to run the container..."
	cd Dockersetup && $(CONTAINER_COMPOSE) -p aclinspector up -d
	@echo "Web UI should be available at http://localhost:8083"

container-status:
	@echo "Using $(CONTAINER_COMPOSE) to show container status..."
	cd Dockersetup && $(CONTAINER_COMPOSE) -p aclinspector ps

container-stop:
	@echo "Using $(CONTAINER_COMPOSE) to stop the container..."
	cd Dockersetup && $(CONTAINER_COMPOSE) -p aclinspector stop

container-clean:
	@echo "Using $(CONTAINER_COMPOSE) to stop and remove the container..."
	cd Dockersetup && $(CONTAINER_COMPOSE) -p aclinspector down --rmi all --volumes

build:
	PYTHONPYCACHEPREFIX=.pyc_cache python3 -m py_compile access-list-inspector.py parsers/cisco/asa.py parsers/fortigate/fortigate.py access-list-web.py

clean:
	rm -rf __pycache__ */__pycache__ .pyc_cache

