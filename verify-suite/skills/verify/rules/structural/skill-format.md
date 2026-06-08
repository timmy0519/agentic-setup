---
name: Skill format checklist
id: skill-format
description: Structural format checklist for skill artifacts — routing correctness, type label consistency, input-shape dispatch
applies_to:
  doctype: [skill-def]
  stage: [verify]
severity: blocking
model_hint: haiku
inputs: [artifact]
bundled_checks: [routing, type-consistency, input-shape-dispatch]
---

## Evaluation prompt

Run each check below against the artifact. Report PASS only if ALL checks pass. Report FAIL listing every failing check with its location.

### Check 1: Routing

Verify the skill description routes correctly:

- The description contains trigger phrases or intent patterns that unambiguously identify when this skill should fire.
- All invocation modes the skill supports (direct invocation, orchestrator-internal, decorator chain) are covered by the description or documented in the SOP.
- No routing collision: the description's trigger phrases do not overlap with another skill's triggers such that a user utterance could plausibly match both. Check against the list of existing skill descriptions provided as context.

Flag as FAIL if trigger phrases are missing, an invocation mode is undocumented, or a collision is identified (name the colliding skill).

### Check 2: Type consistency

Verify the type label in the description matches the SOP content:

- **Label present:** The description contains exactly one primary type label: `[atomic]`, `[orchestrator]`, or `[decorator]`. A `[decorator]` must also carry a compound label (e.g. `[decorator][atomic]`).
- **Atomic consistency:** If labelled `[atomic]`, the SOP must contain no instructions to spawn subagents (no "Agent dispatch", "spawn a subagent", or Agent tool usage).
- **Orchestrator consistency:** If labelled `[orchestrator]`, the SOP must explicitly define subagent structure — each dispatched subagent has a context spec (what it receives) and an output contract (what it returns).
- **Multi-mode consistency:** If the skill supports multiple modes, modes must use conditional branches within shared stages. Flag as FAIL if two modes duplicate the same stage logic as parallel pipelines instead of branching.
- **Decorator consistency:** If labelled `[decorator]`, verify: (a) description includes compound label, (b) description contains a `Triggers on:` clause, (c) description contains a `Bypass:` clause.
- **Decorator conflicts:** The `Triggers on:` reserved keyword must not be a synonym, substring, or superstring of any existing decorator's reserved keyword.
- **Consumer annotation:** Any skill whose SOP receives a parameter matching a reserved keyword must have: (a) `| reserved: <keyword>` suffix in its description, (b) the parameter listed as input in its I/O contract, (c) SOP documentation of what the parameter contains after decorator processing.

Flag as FAIL with the specific sub-check that failed and its location in the artifact.

### Check 3: Input-shape dispatch (multi-mode skills only)

Skip this check if the skill has only one mode (report PASS).

For multi-mode skills, verify explicit mode flags are justified:

- If a mode can be unambiguously inferred from the shape of typed inputs alone (e.g., one mode takes a file path, another takes a query string), an explicit mode flag is redundant and must not exist.
- Explicit mode flags are valid only when input shapes overlap and disambiguation is required.
- Every explicit mode flag must add information beyond what the input shape already provides.

Flag as FAIL if an explicit mode flag exists whose mode could be inferred from input shape alone (name the flag and the distinguishing input shape).

## Boundary examples

**PASS:** Skill description has `[orchestrator]` label, SOP defines 2 subagents each with context spec and output contract, trigger phrases are unique across the skill catalog, single-mode skill so Check 3 is skipped.

**FAIL:** Skill description says `[atomic]` but SOP contains "Spawn a subagent to run verification" (type mismatch). Or: multi-mode skill has `--review` flag but review mode is unambiguously triggered when input is a file path (redundant flag).
