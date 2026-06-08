---
name: workflow-tracking
description: Use when leading or orchestrating a multi-step workflow or agent team — how to track AC-oriented progress with the task-tool MCP vs the native task list, the permissive gate=marker model, and AC origin provenance. Covers routing simple work to the native list vs structured/SOP work to task-tool, resumability/handoff via exec_summary, and how acceptance criteria reference /verify rules with origin:user|ai routing review.
---

## Workflow tracking

How to choose and operate progress-tracking mechanisms when leading a multi-step workflow or agent team.

### A session = one workflow with two aspects

A task-tool session is the parent workflow. It composes two separable aspects:

- **Presenting aspect** (the default member, `meta_key="artifact-flow"`): WHEN/how the user reviews, and which gates persist to disk WITH their ACs even if the user never looks. This is the human-review surface.
- **Powering aspect(s)** (added with `register_workflow` under distinct meta-keys): HOW the work gets done — explore/build/verify lanes.

**The presenting aspect is MANDATORY** — every session must consciously declare how the user reviews. In order of preference: (1) read and apply the `/artifact-flow` skill (best practice — picks a presenting structure matched to the task class); (2) author your own workflow graph; (3) call `init` with no workflow graph to fall back to the built-in general-report skeleton (build → user-review gate → done), which returns a recommendation reminding you it was a fallback. Picking the minimal default is valid; picking it *silently* is the anti-pattern — the choice should be intentional and visible in the record. Powering aspects are optional and added only when a how-the-work-got-done lane is worth tracking separately.

### Routing: native list vs task-tool MCP

- **Simple tasks** (linear, no SOP): use the built-in task list (TaskCreate/TaskUpdate).
- **Structured workflows** (defined SOP, branching states, needs audit trail or resumability): use the task-tool MCP (`mcp__task-tool__init`) with a workflow definition matching the SOP's states.
- **Agent team leads must use task-tool by default** — when leading a team with a multi-step workflow, init a task-tool session. This provides: resumability if the lead crashes, audit trail of decisions, and exec_summary for cold-start handoffs.
- **Workers leading subflows**: if a worker is itself a lead of a nested workflow (e.g., research-lead running plan→search→draft→review→done), it should init its own task-tool session for that subflow.
- **When to upgrade**: if you find yourself needing to track "where am I in this process" beyond a checkbox list, init a workflow.

### Source of truth and handoff

- **Source of truth**: when a task-tool workflow is active, the recorded state is authoritative — don't track position in your context window. Re-ground from `view_current_state` and `view_legal_transitions`.
- **Discovery and handoff**: use `list_sessions()` to find existing workflows, `init(resume_from=path)` to resume. Exec_summary is written for cold-start replacements — another lead should be able to continue from the summary alone.

### Permissive gate model — records, does not enforce

- **task-tool records, it does not enforce**: `gate: true` is a *convention marker* for a human-review checkpoint, not a code gate; ACs and review-evidence attach to ANY state and surface in `get_active_plan` regardless of gate. The tool stays permissive — which states are gates and what ACs to record is the lead's judgment, governed at the prompt layer (this skill + the lead prompt), not by tool refusals. A task-tool gate is advisory and MUST NOT block a dynamic Workflow's execution: the Workflow READS the plan, only the lead WRITES (single-writer). Put gate-shaped/high-level items + gates/ACs in task-tool; detail and inter-agent handoffs stay in the native task list.
- At a gate advance, recording review evidence is one valid path and `advance_without_evidence(reason)` is another — both are legitimate because the gate is advisory and never blocks.

### Acceptance criteria: shared reference + provenance

- **AC = shared reference + provenance**: an AC is a pointer to a `/verify` rule name (the durable standard), not a copied body — the lead can duplicate that pointer into a worker's task or workflow stage so worker and lead work to the *same* standard. Tag each AC `origin: user|ai` truthfully. Origin is NOT a suspicion flag — it ROUTES review to a different lens:
  - `user`-origin → challenge via cost/benefit ("is the user over-scoping their own problem? worth the complexity?", advisory).
  - `ai`-origin → challenge via traceability + necessity ("does this map to a real user ask, or inferred cruft?").
  - Both audited, different lens, neither exempt. The append-only `history` is the evolve/audit log.

### Soft coupling

This skill works standalone. AC graduation references `/verify` rule names (verify-suite plugin) and origin routing aligns with adversarial-review's lenses — those plugins sharpen the review lens but are not required for tracking to function.
