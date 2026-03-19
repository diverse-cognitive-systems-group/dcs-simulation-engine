# syntax=docker/dockerfile:1

# ── Stage 1: Build Python wheel ─────────────────────────────────────────────
FROM python:3.13-slim AS py-builder

WORKDIR /build

RUN pip install --no-cache-dir build

COPY pyproject.toml README.md LICENSE ./
COPY dcs_simulation_engine/ ./dcs_simulation_engine/
COPY games/ ./games/

RUN python -m build --wheel --outdir /dist


# ── Stage 2: Install UI dependencies (bun cache layer) ──────────────────────
FROM oven/bun:1 AS ui-builder

WORKDIR /ui

COPY ui/package.json ui/bun.lock* ./
RUN bun install --frozen-lockfile

# Copy the rest of the UI source (used at runtime via volume-like layer)
COPY ui/ ./


# ── Stage 3: Runtime image ───────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

# Install system deps: MongoDB, bun, supervisor, curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    gnupg \
    curl \
    ca-certificates \
    supervisor \
    procps \
 && curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | \
    gpg --dearmor -o /usr/share/keyrings/mongodb-server-8.0.gpg \
 && echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] \
    https://repo.mongodb.org/apt/debian bookworm/mongodb-org/8.0 main" \
    > /etc/apt/sources.list.d/mongodb-org-8.0.list \
 && apt-get update && apt-get install -y --no-install-recommends \
    mongodb-org \
 && rm -rf /var/lib/apt/lists/*

# Install bun
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:$PATH"

# Install the Python wheel
COPY --from=py-builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Copy game config files (needed at runtime alongside the installed package)
COPY games/ /app/games/

# Copy UI with pre-installed node_modules
COPY --from=ui-builder /ui /app/ui

# MongoDB data directory
RUN mkdir -p /data/db

# Supervisor config: manages mongod, dcs server, and vite dev server
COPY docker/supervisord.conf /etc/supervisor/conf.d/dcs.conf

WORKDIR /app

EXPOSE 8000 5173

ENV MONGO_URI=mongodb://127.0.0.1:27017/
ENV DCS_SERVER_HOST=0.0.0.0
ENV DCS_SERVER_PORT=8000

# Entrypoint: start supervisor in background, then drop into bash
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
