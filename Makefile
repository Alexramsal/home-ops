.PHONY: help test lint check scan status clean

help:
	@echo "Usage:"
	@echo "  make test    - Run 705 pytest suite"
	@echo "  make lint    - Run ruff check and mypy type checks"
	@echo "  make check   - Run both lint and test (pre-push gate)"
	@echo "  make scan    - Run homeops scan pipeline"
	@echo "  make status  - Show pipeline status"
	@echo "  make clean   - Remove cache and temporary files"

test:
	uv run pytest

lint:
	uv run ruff check src tests
	uv run mypy src

check: lint test

scan:
	uv run homeops scan

status:
	uv run homeops status

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
