# Developer interface of the library, runs without further environment variables

venv: .venv/installed

.venv/installed: pyproject.toml
	python3 -m venv .venv
	.venv/bin/pip install --quiet --editable '.[test]'
	touch $@

lint: venv
	.venv/bin/pylint tqem tests

test: venv
	.venv/bin/pytest -q tests

.PHONY: venv lint test
