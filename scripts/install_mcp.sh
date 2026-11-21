#!/usr/bin/env bash
# Register the REINS Edu MCP server (reins_mcp/server.py) with Claude Code, for
# this project only (local scope). Run it once from anywhere; then open Claude
# Code in this folder and /mcp lists "reins". The server must be running for
# most tools (start.sh / start.command / start.bat); validate_exercise works without it.
#
#   REINS_URL       the server (default http://127.0.0.1:8010)
#   REINS_DATA_DIR  the data folder (default: data/ in the REINS Edu folder)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/.venv/bin/python"
[[ -x "$PY" ]] || { echo "No $PY: start REINS Edu once first (./start.sh), which creates it." >&2; exit 1; }
command -v claude >/dev/null || { echo "Claude Code (the 'claude' command) isn't installed." >&2; exit 1; }

ENV=(-e "REINS_URL=${REINS_URL:-http://127.0.0.1:8010}")
[[ -n "${REINS_DATA_DIR:-}" ]] && ENV+=(-e "REINS_DATA_DIR=$REINS_DATA_DIR")

cd "$REPO"
claude mcp remove reins --scope local >/dev/null 2>&1 || true
claude mcp add reins --scope local "${ENV[@]}" -- "$PY" "$REPO/reins_mcp/server.py"
echo "Registered the REINS Edu MCP server for $REPO."
