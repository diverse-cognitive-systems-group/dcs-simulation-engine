# .PHONY tells make that these aren't real files — they're just task names.
# Without this, make might skip a task if a file with the same name exists.
.PHONY: ci coverage docs fmt lint lint-fix test test-fast

# Run all linting checks (on the dcs_simulation_engine/ package here).
lint:
	uv run ruff check
	cd ui && bun lint

lint-fix:
	uv run ruff check --fix
	cd ui && bun lint --fix

# format code in place (on the dcs_simulation_engine/ package here).
fmt:
	uv run ruff format && uv run ruff check --select I --fix
	cd ui && bun format

# Run test suite with line+branch coverage (fails if under 85% per toml)
test:
	uv run pytest

# Run test suite without coverage (faster iteration)
test-fast:
	uv run pytest --no-cov

# Run coverage report without enforcing the fail-under threshold
# HTML report written to htmlcov/index.html
coverage:
	uv run pytest --cov-fail-under=0 --cov-report=html

# Build documentation (MkDocs in this example).
docs:
	uv run mkdocs build --strict -q

pr: fmt lint test

# Meta target — runs everything you want in CI or pre-push.
ci: lint test docs