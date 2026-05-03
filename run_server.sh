#!/usr/bin/env bash
# Start the Galatea WebSocket server standalone.
# Usage: ./run_server.sh [--no-stub] [--port 8765] [--auto-tick]
set -euo pipefail
cd "$(dirname "$0")"
exec uv run python -m server "$@"
