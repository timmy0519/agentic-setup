---
name: Subtraction test (agentic overlay)
id: subtraction-test
description: Domain-specific subtraction criteria for agentic system designs
applies_to:
  doctype: [skill-def, spec-design]
  stage: [write, verify]
---

## Domain context

In agentic systems, also apply these subtraction checks:

- **Script vs. AI check:** Does this component require AI judgment, or could a deterministic script handle it? If a script suffices, the AI component is removable.
- **Orchestrator thickness check:** Is the orchestrator doing judgment work (evaluating content, making quality decisions) instead of pure routing (dispatch, collect, gate)? Judgment work should live in subagent rules or scripts, not the orchestrator.
- **Subagent justification:** Does each subagent role have a distinct evaluation responsibility, or are multiple subagents doing overlapping work that a single subagent could handle?
- **Delegation depth:** Is there a subagent spawning another subagent? Each delegation layer must be justified by a distinct concern — nesting for organizational convenience is removable.
- **Relay detection:** Is there a role whose only function is passing output from one role to another with no transformation, filtering, or judgment? A pure relay adds latency and context cost without value — the upstream role should send directly to the downstream consumer.

For each flagged component, state which agentic subtraction check it fails and why.

## Boundary examples

**PASS:** "Orchestrator dispatches extraction subagents and gates on their results" — clear routing role with distinct delegation responsibility.

**FAIL:** "Convenience wrapper subagent that adds logging around the main subagent's output" — deterministic work that could be a script, not an AI subagent. Fails the script-vs-AI check.

**FAIL:** "Coordinator role receives analysis from researcher and forwards it to builder without modification." — Pure relay; researcher should send directly to builder. Fails the relay detection check.
