
VIRTUAL_ENV ?=
PY = $(VIRTUAL_ENV)/bin/python

ifeq "$(VIRTUAL_ENV)" ""
.PHONY: check_venv
check_venv:
	@echo "not in a virtual env ... could try this:"
	@echo "python3 -m venv .venv; . .venv/bin/activate"
	@exit 1
endif

.PHONY: all
all: install build load

.PHONY: install
install: requirements.txt requirements-test.txt
	uv pip sync requirements-test.txt
	uv pip install -e .

.PHONY: pip-compile
pip-compile: requirements.txt requirements-test.txt

requirements.txt: requirements.in
	uv pip compile $< -o $@

requirements-test.txt: requirements-test.in requirements.txt
	uv pip compile $< -o $@

.PHONY: test
test:
	$(PY) -m pytest

.PHONY: lint
lint:
	$(PY) -m ruff check

.venv:
	uv venv .venv

ifeq "$(realpath $(VIRTUAL_ENV))" "$(realpath .venv)"
.PHONY: clean
clean:
	rm -rf .venv src/*.egg-info
	find . -type d -name __pycache__ -delete
endif


###

.PHONY: build
build: install
	docker build . -t kgrok-remote

.PHONY: load
load: build
	kind load docker-image kgrok-remote
