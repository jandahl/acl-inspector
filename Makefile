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

build:
	PYTHONPYCACHEPREFIX=.pyc_cache python3 -m py_compile access-list-inspector.py parsers/cisco/asa.py parsers/fortigate/fortigate.py access-list-web.py

clean:
	rm -rf __pycache__ */__pycache__ .pyc_cache

