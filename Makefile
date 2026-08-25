PYTHON ?= python3
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
export PYTHONPATH := src

.PHONY: venv install test serve worker ingest init

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt

init:
	$(PY) -m abu_alia init

test:
	$(PY) -m pytest

serve:
	$(PY) -m abu_alia serve --host 127.0.0.1 --port 8080

worker:
	$(PY) -m abu_alia worker

ingest:
	$(PY) -m abu_alia ingest fixture --limit 10
