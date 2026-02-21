# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm

# Install git + optional SSH client for GitHub/Bitbucket, plus minimal build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client ca-certificates curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install flyctl exactly as per Fly.io docs
RUN curl -L https://fly.io/install.sh | sh

# Make flyctl available on PATH for all users
ENV PATH="/root/.fly/bin:${PATH}"

# Keep it minimal; no compilers unless your deps need them.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Cache-friendly deps layer
COPY pyproject.toml uv.lock* ./

# Install deps - include dev deps for devcontainer
RUN uv sync --extra dev

# App code
COPY . .
