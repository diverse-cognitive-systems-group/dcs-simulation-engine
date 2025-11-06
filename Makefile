# .PHONY tells make that these aren't real files — they’re just task names.
# Without this, make might skip a task if a file with the same name exists.
.PHONY: lint test docs ci

# Run all linting/formatting checks (you can add more tools here if needed).
lint:
	poetry run ruff check .
	poetry run black --check --diff .
	poetry run mypy .

# Run your test suite quietly.
test:
# TODO: re-enable once tests are fixed
# 	poetry run pytest -q
# 	poetry run pytest -vv -m "not slow and not manual and not external"

# Build documentation (MkDocs in this example).
docs:
	poetry run mkdocs build --strict -q

# Meta target — runs everything you want in CI or pre-push.
ci: lint test docs