# syntax=docker/dockerfile:1
FROM astral/uv:python3.13-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    NVM_DIR=/usr/local/nvm \
    NVM_SYMLINK_CURRENT=true \
    BUN_INSTALL=/opt/bun \
    PATH="/opt/venv/bin:/opt/bun/bin:/usr/local/nvm/current/bin:/root/.fly/bin:/app/ui/node_modules/.bin:${PATH}" 

# Install the base toolchain needed for both the Python API and Bun/Vite UI.
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    ca-certificates \
    curl \
    gh \
    git \
    gnupg \
    gpg \
    locales \
    openssh-client \
    unzip \
    zsh \
    && rm -rf /var/lib/apt/lists/*

# make zsh the default shell
RUN chsh -s $(which zsh)

RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

# install eza
RUN mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://raw.githubusercontent.com/eza-community/eza/main/deb.asc | gpg --dearmor -o /etc/apt/keyrings/gierens.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/gierens.gpg] http://deb.gierens.de stable main" | tee /etc/apt/sources.list.d/gierens.list \
    && chmod 644 /etc/apt/keyrings/gierens.gpg /etc/apt/sources.list.d/gierens.list \
    && apt update \
    && apt install -y eza \
    && rm -rf /var/lib/apt/lists/*

# upgrade all packages to ensure we have the latest security updates
RUN  apt update \
    && apt upgrade -y \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js via nvm so the version can be managed consistently inside
# the dev container.
RUN mkdir -p "${NVM_DIR}" \
    && bash -lc 'curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | PROFILE=/dev/null bash' \
    && bash -lc '. "${NVM_DIR}/nvm.sh" && nvm install --lts && nvm alias default "lts/*" && nvm use default'

# Install Fly CLI for the deploy/debug workflows used by this repo.
RUN curl -fsSL https://fly.io/install.sh | sh

# Install Bun so the UI can run from inside the dev container.
RUN curl -fsSL https://bun.sh/install | bash

# Install the official Codex CLI for Linux so it is available inside the
# dev container without relying on the host editor extension binary.
RUN npm i -g @openai/codex@latest

# Create the project virtualenv outside /app so it survives the workspace bind
# mount used by the dev container. The actual `uv sync` happens after the repo
# is mounted by devcontainer.json.
RUN uv python install 3.13 \
    && uv venv --python 3.13 "${UV_PROJECT_ENVIRONMENT}"

# Keep Codex config inside the container, but let auth be mounted in from the
# host so the CLI can reuse an existing login without copying secrets into git.
RUN mkdir -p /root/.codex \
    && printf '%s\n' \
    'model = "gpt-5.4"' \
    'model_reasoning_effort = "high"' \
    'approval_policy = "never"' \
    'sandbox_mode = "danger-full-access"' \
    > /root/.codex/config.toml

WORKDIR /app

# The source tree is bind-mounted onto /app at runtime, so this image acts as a
# development base rather than copying the project in during build.
RUN printf '%s\n' \
    'export NVM_DIR="/usr/local/nvm"' \
    '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"' \
    'alias dcs="uv run dcs"' \
    >> /root/.bashrc \
    && printf '%s\n' \
    'export NVM_DIR="/usr/local/nvm"' \
    '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"' \
    'alias dcs="uv run dcs"' \
    >> /root/.zshrc

# set the ~/.zshrc file 
COPY .devcontainer/zshrc /root/.zshrc 

# source the .zshrc file to ensure the aliases are available in the dev container
RUN zsh -c "source /root/.zshrc"

# ! NOTE: Make sure to use --network=host when running the container so the API server is reachable at localhost:8000
