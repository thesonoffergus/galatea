#!/usr/bin/env bash
# Start the Galatea WebSocket server and print instructions for launching Godot.
set -euo pipefail
cd "$(dirname "$0")"

echo "Starting Galatea WebSocket server..."
uv run python -m server --stub &
SERVER_PID=$!

cleanup() {
    echo ""
    echo "Stopping server (PID $SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 2
echo ""
echo "=========================================================="
echo "  Server running on ws://localhost:8765  (StubRunner mode)"
echo ""
echo "  Open the Godot 4 editor and load:  client/"
echo "  Then press F5 (Play) to launch the game."
echo ""
echo "  To use a real LLM: ./run_server.sh --no-stub"
echo "  To enable auto-tick: ./run_server.sh --auto-tick"
echo "=========================================================="
echo ""

wait "$SERVER_PID"
