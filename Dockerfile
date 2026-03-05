# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm

# Install git + optional SSH client for GitHub/Bitbucket, plus minimal build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client ca-certificates curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Keep it minimal; no compilers unless your deps need them.
ENV POETRY_VIRTUALENVS_CREATE=false \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Cache-friendly deps layer
COPY pyproject.toml uv.lock* ./

# Install deps
RUN uv sync

# App code
COPY . .