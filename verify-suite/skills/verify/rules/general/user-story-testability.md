---
name: User stories must be testable
id: user-story-testability
description: 'Every user story must have at least one acceptance criterion or testable
  observable outcome. A story that cannot be tested cannot be verified as complete.

  '
applies_to:
  doctype: [spec-req]
  stage: [write, verify]
severity: advisory
model_hint: sonnet
inputs: [artifact]
constituent_checks: [user-story-testability]
---

## Evaluation prompt

Every user story must have at least one acceptance criterion or testable observable outcome. A story that cannot be tested cannot be verified as complete.


**Illustrations of this principle** (non-exhaustive — apply the principle even
to cases not listed here):

- **user-story-testability**: User stories without "given/when/then" criteria, observable outcomes, or any other testable acceptance condition.


For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "Given a new user, when they run sync for the first time, then all transactions from the last 30 days appear in the UI."


**FAIL:** "As a user, I want good performance." — No observable outcome, no measurable criterion.

