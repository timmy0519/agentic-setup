---
name: Don't introduce what you don't need
id: design-economy
description: 'Design artifacts should not include redundant data access, duplicate
  interaction patterns, or components that don''t carry their weight. Every element
  must justify its existence. Apply the subtraction test: if removing it doesn''t
  break a user story, it shouldn''t be there.

  '
applies_to:
  doctype: [spec-design]
  stage: [write, verify]
severity: advisory
model_hint: opus
inputs: [artifact, requirements]
constituent_checks: [no-redundant-fetch, no-duplicate-patterns, subtraction-test]
---

## Evaluation prompt

Design artifacts should not include redundant data access, duplicate interaction patterns, or components that don't carry their weight. Every element must justify its existence. Apply the subtraction test: if removing it doesn't break a user story, it shouldn't be there.


**Illustrations of this principle** (non-exhaustive — apply the principle even
to cases not listed here):

- **no-redundant-fetch**: Proposed data reads or fetches that duplicate data already available through existing mechanisms in the design.

- **no-duplicate-patterns**: User stories or interaction patterns described with different nouns but identical structure — should be unified.

- **subtraction-test**: Components, steps, or mechanisms that can be removed without losing any user-story functionality — dead weight.


For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "Each component traces to at least one user story. Removing any component breaks at least one flow."


**FAIL:** "Add a caching layer for rule files." — Rules are read once at startup; caching adds complexity without measurable benefit.

