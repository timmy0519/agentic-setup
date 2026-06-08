#!/usr/bin/env bash
# Launch the task-tool MCP server with the src/ layout on PYTHONPATH.
# Resolves its own directory so it works regardless of CWD or how the plugin
# root is substituted — avoids ${CLAUDE_PLUGIN_ROOT} interpolation in the env
# block, which Claude Code does not expand (only command/args are expanded).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec env PYTHONPATH="$DIR/src" uv run --directory "$DIR" python -m task_tool
