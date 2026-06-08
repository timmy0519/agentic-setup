---
name: Language precision
id: language-precision
description: 'Spec language must be precise and committed, not tentative or vague.
  Scan for hedging phrases, vague qualifiers, and unbounded universals. Every claim
  must specify what, when, and how much — not defer to the reader''s interpretation.

  '
applies_to:
  doctype: [spec-req, spec-design, spec-task, research-note, skill-def, claude-md, memory, wishlist, project-index, verify-rule]
  stage: [write, verify]
severity: blocking
model_hint: sonnet
inputs: [artifact]
constituent_checks: [no-vague-language, vague-qualifiers, implicit-universals]
---

## Evaluation prompt

Spec language must be precise and committed, not tentative or vague. Scan for hedging phrases, vague qualifiers, and unbounded universals. Every claim must specify what, when, and how much — not defer to the reader's interpretation.


**Illustrations of this principle** (non-exhaustive — apply the principle even
to cases not listed here):

- **no-vague-language**: Tentative or hedging phrasing: "should consider", "maybe", "perhaps", "could be", "could potentially", "might", "might want to", "it would be nice", "ideally", "TBD", "TODO" outside open-questions sections.

- **vague-qualifiers**: Vague qualifiers in user stories and in-scope items: "appropriate", "sufficient", "reasonable", "properly", "as needed", "etc.", "and so on", "handle gracefully", "correctly", "suitably", "adequate".

- **implicit-universals**: Unbounded universal quantifiers: "all", "every", "any" without stated exceptions or cardinality bounds.


For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "The orchestrator uses YAML because prompts need unconstrained prose." — Decision stated as made, no hedging.


**FAIL:** "All inputs should be appropriately validated." — Vague qualifier ("appropriately") + unbounded universal ("all") + hedging ("should").

