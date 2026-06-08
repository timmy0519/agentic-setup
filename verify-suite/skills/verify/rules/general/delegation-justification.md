---
name: Delegation boundaries must be justified
id: delegation-justification
description: 'Every delegation boundary must justify what the delegated role uniquely contributes and provide sufficient context for autonomous execution. Applies to any manager/specialist decomposition, role assignment, or subagent dispatch.'
applies_to:
  doctype: [spec-design, skill-def]
  stage: [write, verify]
severity: advisory
model_hint: opus
inputs: [artifact]
constituent_checks: [delegation-rationale, no-manager-as-executor, spawn-specification]
---

## Evaluation prompt

Every delegation boundary must justify what the delegated role uniquely contributes and provide sufficient context for autonomous execution.

**Illustrations of this principle** (non-exhaustive — apply the principle even to cases not listed here):

- **delegation-rationale**: Every classification of work to a role has a delegation rationale — not just a label. "Assigned to: builder" is insufficient; "Assigned to builder because this requires code generation expertise and isolated file scope" justifies the boundary.

- **no-manager-as-executor**: No step classified as "manager" is repeatable execution work. If a manager role does the same work a specialist does, the delegation boundary is unjustified — the manager should delegate, not execute.

- **spawn-specification**: Every subagent dispatch provides sufficient context for autonomous execution — the subagent receives clear inputs, constraints, and expected outputs. Under-specified spawns create implicit dependencies on shared context that may not exist.

For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "Builder role receives: source SOP path, role-assignment table, and output directory. Rationale: builder needs code generation for template substitution, which is distinct from the analyst's classification work." — Clear rationale and sufficient spawn context.

**PASS:** "Lead reviews output quality but does not write artifacts — delegates all writing to specialist roles." — Manager does not execute specialist work.

**FAIL:** "Role: analyst. Responsibilities: analyze the input." — No rationale for why this is a separate role rather than inline work.

**FAIL:** "Spawn subagent to handle Stage 3." — Under-specified; no inputs, constraints, or expected outputs provided.

**FAIL:** "Lead writes the compilation report after collecting teammate outputs." — Manager executing repeatable artifact-writing work that a specialist should handle.
