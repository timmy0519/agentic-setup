---
name: Design changes don't require editing unrelated things
id: design-extensibility
description: 'The system must be extensible without modifying existing artifacts or
  relying on human memory. Check for centralized registries without sync mechanisms,
  dispatch logic that enumerates names instead of matching patterns, and convention-based
  instructions instead of enforcing mechanisms.

  '
applies_to:
  doctype: [spec-design]
  stage: [write, verify]
severity: advisory
model_hint: sonnet
inputs: [artifact]
constituent_checks: [ssot-maintenance, open-closed-principle, no-convention-as-design]
---

## Evaluation prompt

The system must be extensible without modifying existing artifacts or relying on human memory. Check for centralized registries without sync mechanisms, dispatch logic that enumerates names instead of matching patterns, and convention-based instructions instead of enforcing mechanisms.


**Illustrations of this principle** (non-exhaustive — apply the principle even
to cases not listed here):

- **ssot-maintenance**: Centralized artifacts (registries, indexes, config files) that describe other entities but have no mechanism to stay in sync when those entities change.

- **open-closed-principle**: Dispatch logic, routing, or type handling that enumerates specific names instead of matching patterns — adding a new type requires editing the dispatch.

- **no-convention-as-design**: Instructions like "remember to", "users should", "by convention" instead of concrete mechanisms (validation, linting, automation) that enforce the intended behavior.


For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "New rule types are discovered by glob pattern (rules/**/*.md) — adding a rule requires only creating a file."


**FAIL:** "When adding a new check, remember to update the registry and the config file." — Two manual edits for one logical change.

