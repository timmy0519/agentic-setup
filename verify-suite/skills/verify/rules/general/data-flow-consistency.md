---
name: Data flows must be internally consistent
id: data-flow-consistency
description: 'Parallel branches, concurrent steps, and stated mechanisms must not
  contradict each other or hide data dependencies. Check for parallel branches sharing
  input without isolation, concurrent steps with hidden dependencies, and mechanisms
  that violate stated constraints.

  '
applies_to:
  doctype: [spec-design]
  stage: [write, verify]
severity: blocking
model_hint: sonnet
inputs: [artifact, requirements]
constituent_checks: [parallel-data-dependency, concurrent-execution-consistency, no-self-contradiction]
---

## Evaluation prompt

Parallel branches, concurrent steps, and stated mechanisms must not contradict each other or hide data dependencies. Check for parallel branches sharing input without isolation, concurrent steps with hidden dependencies, and mechanisms that violate stated constraints.


**Illustrations of this principle** (non-exhaustive — apply the principle even
to cases not listed here):

- **parallel-data-dependency**: Parallel branches sharing an input without stated isolation — filtering vs aggregation ordering ambiguity.

- **concurrent-execution-consistency**: Steps in a concurrent group where one depends on the output of another in the same group — hidden serialization requirement.

- **no-self-contradiction**: Design mechanisms that violate constraints from requirements.md — the design says one thing, the requirements say another.


For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "Parallel rule evaluations are independent — each receives a read-only copy of the artifact. Results are merged after all complete."


**FAIL:** "Steps A and B run concurrently. Step B uses Step A's output." — Hidden serialization dependency in a concurrent group.

