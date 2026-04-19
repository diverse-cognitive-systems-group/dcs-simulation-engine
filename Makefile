# .PHONY tells make that these aren't real files — they're just task names.
# Without this, make might skip a task if a file with the same name exists.
.PHONY: ci docs fmt lint lint-fix test test-fast test-live

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

# Run test suite quietly
test:
	uv run pytest -m "not live" -rs

test-fast:
	uv run pytest -m "not live and not slow" --no-cov -ra

test-live:
	uv run pytest -m live -ra --no-cov

# Build documentation (MkDocs in this example).
docs:
	uv run mkdocs build --strict -q

pr: fmt lint test

# Meta target — runs everything you want in CI or pre-push.
ci: lint test docs
