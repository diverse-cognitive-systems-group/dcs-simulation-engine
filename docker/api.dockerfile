# syntax=docker/dockerfile:1

ARG PYTHON_BASE_IMAGE=ghcr.io/astral-sh/uv:python3.13-bookworm-slim

FROM ${PYTHON_BASE_IMAGE} AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY dcs_simulation_engine/ ./dcs_simulation_engine/
COPY examples/run_configs/ ./examples/run_configs/
COPY database_seeds/ ./database_seeds/

RUN uv sync --frozen --no-dev


FROM ${PYTHON_BASE_IMAGE} AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
ENV MONGO_URI="mongodb://mongo:27017/"
ENV DCS_SERVER_HOST="0.0.0.0"
ENV DCS_SERVER_PORT="8000"

COPY --from=builder /app /app

EXPOSE 8000

CMD ["dcs", "server"]
