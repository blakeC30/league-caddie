# Development commands for the backend.
# Run targets with: make <target>

# Common environment for all test targets.
# BCRYPT_ROUNDS=4 cuts bcrypt cost 64× vs the production default of 12 —
# the rounds value is stored inside the hash, so verify_password still works.
TEST_ENV := TEST_DATABASE_URL=postgresql://league_caddie:league_caddie@localhost:5432/league_caddie_test \
            ENVIRONMENT=test \
            BCRYPT_ROUNDS=4

# --reload-dir app restricts the file watcher to the app/ source directory.
# Without this, uvicorn watches .venv/, __pycache__/, etc. and restarts in
# an infinite loop as Python writes .pyc files during imports.
dev:
	uv run uvicorn app.main:app --reload --reload-dir app

# Fast test run — parallel workers, no coverage instrumentation.
# Use this for quick feedback during development.
test:
	$(TEST_ENV) uv run pytest tests/ -q

# Run a single test file (e.g. make test-file FILE=tests/test_auth.py)
test-file:
	$(TEST_ENV) uv run pytest $(FILE) -v

# Coverage run — parallel workers + coverage instrumentation.
# Slower than `make test`; use before merging or to verify the coverage gate.
cov:
	$(TEST_ENV) uv run pytest tests/ --cov=app --cov-report=term-missing -q

lint:
	uv run ruff check app/ tests/

.PHONY: dev test test-file cov lint
