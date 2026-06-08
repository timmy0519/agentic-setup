---
name: Content stays in its layer
id: content-stays-in-layer
description: 'Each artifact type has a defined scope — requirements describe what,
  design describes how. Content that belongs in another layer is a violation. Check
  that requirements contain no implementation details or design decisions, that design
  contains no user stories, and that no specifics appear without traceability to stated
  user input.

  '
applies_to:
  doctype: [spec-req, spec-design, spec-task]
  stage: [write, verify]
severity: advisory
model_hint: sonnet
inputs: [artifact]
constituent_checks: [no-implementation-details, no-design-decisions, no-user-stories, no-ungrounded-extrapolation]
---

## Evaluation prompt

Each artifact type has a defined scope — requirements describe what, design describes how. Content that belongs in another layer is a violation. Check that requirements contain no implementation details or design decisions, that design contains no user stories, and that no specifics appear without traceability to stated user input.


**Illustrations of this principle** (non-exhaustive — apply the principle even
to cases not listed here):

- **no-implementation-details**: Tool names, code references, API endpoints, internal mechanics, or technology choices in requirements.

- **no-design-decisions**: Architecture choices, algorithm selection, component decomposition, or data model decisions embedded in requirements.

- **no-user-stories**: "As a user, I want..." or user-story phrasing appearing in design.md.

- **no-ungrounded-extrapolation**: Specifics in user stories not traceable to stated user input or standard domain terms — the agent introduced design-level detail.


For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "User can export data in a portable format." (requirements) — States what without prescribing how.


**FAIL:** "Use SQLite with WAL mode for the local cache." (requirements) — Implementation detail that belongs in design.md.

