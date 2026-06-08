# workflow-tracking

A Claude Code plugin for AC-oriented progress tracking across multi-step workflows and agent teams.

## What it ships

| Component | Path | Purpose |
|-----------|------|---------|
| **task-tool MCP** | `mcp/` (declared in `.mcp.json`) | stdio MCP server providing workflow state machines, append-only history, ACs, review evidence, resumable sessions, and `get_active_plan`. Launched via `uv run --directory ${CLAUDE_PLUGIN_ROOT}/mcp task-tool`. |
| **workflow-tracking skill** | `skills/workflow-tracking/SKILL.md` | The guidance that decides *when* to use task-tool vs the native task list, the permissive `gate=marker` model, and AC origin provenance. Ships the former CLAUDE.md "Workflow tracking" rules without needing a CLAUDE.md (plugins can't ship one). |
| **advance nudge hook** | `hooks/hooks.json` + `hooks/advance_nudge.sh` | A non-blocking `PreToolUse` hook on the task-tool advance tool. At a workflow-state advance it injects an advisory reminder to record review evidence (or `advance_without_evidence(reason)`) at gate checkpoints — both valid, the gate never blocks. |

## Core model

- **Routing**: simple/linear work → native task list; structured/SOP/team work → task-tool MCP. Team leads use task-tool by default for resumability + cold-start handoff via exec_summary.
- **Gate = advisory marker**: task-tool *records*, it does not *enforce*. `gate: true` flags a human-review checkpoint; governance lives at the prompt layer (the bundled skill + the lead prompt), not in tool refusals.
- **AC = shared reference + provenance**: an acceptance criterion points to a `/verify` rule name (duplicable into a worker's stage so worker and lead hold the same standard) and carries `origin: user|ai`, which routes review to a different lens rather than flagging suspicion.

## Coupling

Works **standalone**. Soft-couples to:
- **verify-suite** — AC graduation references `/verify` rule names as the durable standard.
- **adversarial-review** — `origin: user|ai` routing aligns with its review lenses (cost/benefit vs traceability/necessity).

Neither is required for tracking to function.
