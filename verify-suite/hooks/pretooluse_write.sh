#!/usr/bin/env bash
# PreToolUse hook for Write|Edit — inject applicable rule manifest before file write.
set -uo pipefail
LOG=/tmp/hook-pretooluse-write.log

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
[ "$TOOL" != "Write" ] && [ "$TOOL" != "Edit" ] && exit 0

FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[ -z "$FILE" ] && exit 0

LIB="${CLAUDE_PLUGIN_ROOT}/lib"
DOCTYPE=$(python3 "$LIB/doctype_from_path.py" "$FILE" 2>/dev/null)

# Empty doctype = unknown or explicitly excluded → no inject
if [ -z "$DOCTYPE" ]; then
    echo "[$(date '+%H:%M:%S')] skip $FILE (no doctype match)" >> "$LOG"
    exit 0
fi

MANIFEST=$(python3 "$LIB/select_rules.py" --doctype "$DOCTYPE" --stage write 2>/dev/null)
[ -z "$MANIFEST" ] && exit 0

echo "[$(date '+%H:%M:%S')] inject doctype=$DOCTYPE file=$FILE" >> "$LOG"

# Emit JSON for Claude Code: additionalContext at top level, NOT decision/allow
jq -nc --arg msg "Writing $DOCTYPE artifact: $FILE

Applicable rules (per applies_to metadata):
$MANIFEST

Full rule text at ${CLAUDE_PLUGIN_ROOT}/skills/verify/rules/. Apply Tier 1 blocking rules first; T2/T3 per section judgment." \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $msg}}'

exit 0
