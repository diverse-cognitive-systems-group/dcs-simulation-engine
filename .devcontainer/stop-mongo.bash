#!/bin/bash
set -euo pipefail

# dumps the contents of the database to the ./runs directory
dcs dump ./runs

# stops the database
docker compose -f .devcontainer/dev.compose.yml down --volumes