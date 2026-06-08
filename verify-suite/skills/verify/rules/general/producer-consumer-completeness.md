---
name: Every role output must have a consumption path
id: producer-consumer-completeness
description: 'In multi-role SOPs and team designs, every declared output or written artifact must have a corresponding step in some role''s SOP that reads or acts on it. Orphaned outputs indicate a broken pipeline — the producer writes state that no consumer ever reads. Also checks for contradictions between lifecycle declarations (e.g., Second-Run Behavior) and role output behavior.'
applies_to:
  doctype: [spec-design]
  stage: [write, verify]
severity: advisory
model_hint: sonnet
inputs: [artifact]
constituent_checks: [orphaned-output, lifecycle-contradiction, missing-consumption-step]
---

## Evaluation prompt

In multi-role SOPs and team designs, every declared output or written artifact must have a corresponding step in some role's SOP that reads or acts on it. An orphaned output is a pipeline defect — the producer writes state that no consumer ever reads.

**Illustrations of this principle** (non-exhaustive — apply the principle even to cases not listed here):

- **orphaned-output**: A role's SOP writes an artifact (file, message, state update) that no other role's SOP references as an input or precondition. The output exists but has no consumer.

- **lifecycle-contradiction**: A lifecycle declaration (e.g., "each session is independent, starts fresh") contradicts a role's output behavior (e.g., a role writes a resume plan for next session). The declaration and the behavior cannot both be true.

- **missing-consumption-step**: An I/O contract declares an output, and another role logically needs it, but no explicit SOP step reads it. The dependency is implicit — it works only if the consuming role happens to look for it, not because the SOP instructs it to.

For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "Note-taker writes Next Session Plan to Layer 2 note. Teacher's Phase 0 step 5 reads the Layer 2 note and offers resume options when topic is in_progress." — Output has an explicit consumption step.

**PASS:** "Researcher writes materials to temp file. Teacher queries Researcher via SendMessage for per-section slices." — Output consumed via standby query pattern.

**FAIL:** "Note-taker writes a Next Session Plan section at wrap-up. Second-Run Behavior says 'each session starts fresh.' No SOP step reads the Next Session Plan." — Orphaned output + lifecycle contradiction.

**FAIL:** "Builder produces a schema file at Stage 2. Deployer needs the schema at Stage 5 but no step in Deployer's SOP reads or references the schema file." — Missing consumption step; dependency is implicit.
