#!/usr/bin/env bash
# PreToolUse nudge for task-tool workflow-state advances.
# Reads the hook JSON from stdin (ignored — advisory only) and emits a brief
# additionalContext reminder. Non-blocking, always exit 0.

# Drain stdin so the producing process doesn't get SIGPIPE.
cat >/dev/null 2>&1 || true

cat <<'JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "Advancing a workflow state: if this is a gate:true review checkpoint, confirm review evidence is recorded (record_review_evidence) or advance_without_evidence(reason); both valid — the gate is advisory, never blocks."
  }
}
JSON

exit 0
