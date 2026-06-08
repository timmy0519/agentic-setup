---
name: Open questions must be resolved or explicitly deferred
id: uncertainty-managed
description: 'Markers of uncertainty (TBD, TODO, "needs research") must be resolved,
  have a researched default, or be deferred with rationale. Task plans must have an
  open questions section to track unresolved items.

  '
applies_to:
  doctype: [research-note, spec-design, memory]
  stage: [write, verify]
severity: advisory
model_hint: sonnet
inputs: [artifact]
constituent_checks: [open-questions-resolved, open-questions-section]
---

## Evaluation prompt

Markers of uncertainty (TBD, TODO, "needs research") must be resolved, have a researched default, or be deferred with rationale. Task plans must have an open questions section to track unresolved items.


**Illustrations of this principle** (non-exhaustive — apply the principle even
to cases not listed here):

- **open-questions-resolved**: TBD, TODO, or "needs research" markers in requirements that are not resolved or explicitly deferred with rationale.

- **open-questions-section**: Task.md files missing an "Open questions" or "Questions" section.


For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "**Deferred:** Auth provider choice — blocked on security team review (ETA: next sprint). Default: OAuth2 via existing gateway."


**FAIL:** "TBD: figure out auth later." — No rationale, no default, no timeline.

