---
name: End-to-end workflows must be visible
id: e2e-workflow-visibility
description: 'Every user story or use case must have a complete flow visible in diagrams,
  showing all steps, inputs, outputs, and decision points. Check for missing diagrams
  and use cases without end-to-end flow coverage.

  '
applies_to:
  doctype: [spec-design]
  stage: [write, verify]
severity: advisory
model_hint: sonnet
inputs: [artifact]
constituent_checks: [e2e-workflow-coverage, flow-or-architecture-diagram]
---

## Evaluation prompt

Every user story or use case must have a complete flow visible in diagrams, showing all steps, inputs, outputs, and decision points. Check for missing diagrams and use cases without end-to-end flow coverage.


**Illustrations of this principle** (non-exhaustive — apply the principle even
to cases not listed here):

- **e2e-workflow-coverage**: Use cases or user stories without a corresponding sequence or flow diagram showing the full end-to-end path.

- **flow-or-architecture-diagram**: Design file with no Mermaid diagram present at all — at minimum, one architecture or flow diagram is required.


For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "Each of the 3 user stories has a sequence diagram showing actor → system → storage → response flow."


**FAIL:** Design describes 5 use cases in prose with no diagrams — reviewer cannot trace end-to-end behavior visually.

