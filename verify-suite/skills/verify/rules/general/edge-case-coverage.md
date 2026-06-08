---
name: Edge cases must be addressed
id: edge-case-coverage
description: 'Every requirement with variable inputs, state transitions, or error
  paths must address the non-happy-path cases. Check for missing scenarios (first-run,
  repeat, empty, boundary), missing boundary conditions (zero, one, max/overflow),
  missing error/failure handling, and irreversible actions without sufficient trigger
  criteria.

  '
applies_to:
  doctype: [spec-task, spec-design]
  stage: [write, verify]
severity: advisory
model_hint: sonnet
inputs: [artifact]
constituent_checks: [scenario-coverage, boundary-conditions, missing-error-paths, irreversible-action-check]
---

## Evaluation prompt

Every requirement with variable inputs, state transitions, or error paths must address the non-happy-path cases. Check for missing scenarios (first-run, repeat, empty, boundary), missing boundary conditions (zero, one, max/overflow), missing error/failure handling, and irreversible actions without sufficient trigger criteria.


**Illustrations of this principle** (non-exhaustive — apply the principle even
to cases not listed here):

- **scenario-coverage**: State-implying or variable-cardinality items without first-run, repeat-run, empty input, or boundary input scenarios addressed.

- **boundary-conditions**: Countable or sized inputs without zero, one, and max/overflow cases addressed.

- **missing-error-paths**: Happy-path actions with no corresponding error or failure handling mentioned anywhere in scope.

- **irreversible-action-check**: Irreversible actions (delete, overwrite, send, publish) with only necessary trigger criteria — missing sufficient criteria like confirmation, undo window, or idempotency guard.


For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "If sync fails mid-batch, already-synced transactions are preserved and the user sees which items failed with retry option."


**FAIL:** "User can delete their account." — No confirmation step, no grace period, no mention of what happens to their data.

