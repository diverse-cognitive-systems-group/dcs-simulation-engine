# syntax=docker/dockerfile:1
FROM python:3.10.13-slim

# Install git + optional SSH client for GitHub/Bitbucket, plus minimal build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client ca-certificates curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install flyctl exactly as per Fly.io docs
RUN curl -L https://fly.io/install.sh | sh

# Make flyctl available on PATH for all users
ENV PATH="/root/.fly/bin:${PATH}"

# Keep it minimal; no compilers unless your deps need them.
ENV POETRY_VIRTUALENVS_CREATE=false \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Pin Poetry to stable 2.1.x
RUN pip install --no-cache-dir "poetry==2.1.4"

WORKDIR /app

# Cache-friendly deps layer
COPY pyproject.toml poetry.lock* ./

# Install deps - include dev deps for devcontainer
RUN poetry install --no-root --with dev

# App code
COPY . .