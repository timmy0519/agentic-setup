---
name: Decisions must be justified
id: decisions-justified
description: 'Every stated design choice must include the reason it was made, not
  just the choice itself. Check that each decision has inline rationale explaining
  why this approach over alternatives.

  '
applies_to:
  doctype: [spec-design, spec-decisions]
  stage: [write, verify]
severity: advisory
model_hint: sonnet
inputs: [artifact]
constituent_checks: [decisions-have-rationale]
---

## Evaluation prompt

Every stated design choice must include the reason it was made, not just the choice itself. Check that each decision has inline rationale explaining why this approach over alternatives.


**Illustrations of this principle** (non-exhaustive — apply the principle even
to cases not listed here):

- **decisions-have-rationale**: Statements like "we use X" or "the system does Y" without a "because..." clause or rationale section explaining the reasoning.


For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "Rules are stored as markdown files because the evaluation prompt needs unconstrained prose that YAML values handle poorly."


**FAIL:** "The compiler uses Python." — No rationale for the choice.

