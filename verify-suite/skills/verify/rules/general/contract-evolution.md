---
name: Contracts must support evolution
id: contract-evolution
description: 'Every interface, contract, or named identifier the design exposes must
  address what happens when it changes. Check for interfaces without evolution stories
  and named identifiers without uniqueness enforcement.

  '
applies_to:
  doctype: [spec-design]
  stage: [write, verify]
severity: advisory
model_hint: sonnet
inputs: [artifact]
constituent_checks: [contract-stability, namespace-collision-rules]
---

## Evaluation prompt

Every interface, contract, or named identifier the design exposes must address what happens when it changes. Check for interfaces without evolution stories and named identifiers without uniqueness enforcement.


**Illustrations of this principle** (non-exhaustive — apply the principle even
to cases not listed here):

- **contract-stability**: Interfaces, APIs, or contracts with no mention of versioning, deprecation strategy, or what happens to existing consumers when the contract changes.

- **namespace-collision-rules**: Named identifiers (IDs, slugs, keys) with no stated uniqueness constraint, naming convention, or collision prevention mechanism.


For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "Rule IDs are kebab-case slugs, unique per directory. The compiler rejects duplicates at build time."


**FAIL:** "Each rule has an ID." — No uniqueness enforcement, no naming convention, no collision handling.

