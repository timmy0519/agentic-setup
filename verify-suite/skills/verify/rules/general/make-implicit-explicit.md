---
name: Make implicit things explicit
id: make-implicit-explicit
description: 'Assumptions, tradeoffs, dependencies, and ordering must be stated, not
  left for the reader to infer. If it is load-bearing, state it. Check for unstated
  tradeoffs, fragile assumptions, hidden data dependencies, and implicit sequencing.

  '
applies_to:
  doctype: [spec-req, spec-design, spec-task]
  stage: [write, verify]
severity: advisory
model_hint: sonnet
inputs: [artifact]
constituent_checks: [tradeoff-explicitness, assumption-fragility, data-dependencies, assumed-ordering]
---

## Evaluation prompt

Assumptions, tradeoffs, dependencies, and ordering must be stated, not left for the reader to infer. If it is load-bearing, state it. Check for unstated tradeoffs, fragile assumptions, hidden data dependencies, and implicit sequencing.


**Illustrations of this principle** (non-exhaustive — apply the principle even
to cases not listed here):

- **tradeoff-explicitness**: Design decisions listing benefits without stating what was traded away — every choice has a cost.

- **assumption-fragility**: Assumptions stated without consequence analysis — what happens if this assumption becomes false, and how hard is recovery?

- **data-dependencies**: Shared data artifacts between in-scope items with no stated dependency relationship (who produces, who consumes, what order).

- **assumed-ordering**: Words like "then", "after", "next" implying sequence without explicit ordering constraints or dependency declarations.


For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "Assumes single-user access. If multi-user is needed later, the sync layer must be replaced — estimated 2-week effort."


**FAIL:** "After the user authenticates, fetch their profile." — Implicit ordering with no stated dependency or failure handling if auth fails.

