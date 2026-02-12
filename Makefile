# .PHONY tells make that these aren't real files — they’re just task names.
# Without this, make might skip a task if a file with the same name exists.
.PHONY: lint test docs ci

# Run all linting/formatting checks (on the dcs_simulation_engine/ package here).
lint:
	poetry run ruff check dcs_simulation_engine/
	poetry run black --check --diff dcs_simulation_engine

# Run test suite quietly.
test:
	poetry run pytest -m unit -q && poetry run pytest -m functional -q

# Build documentation (MkDocs in this example).
docs:
	poetry run mkdocs build --strict -q

# Meta target — runs everything you want in CI or pre-push.
ci: lint test docs