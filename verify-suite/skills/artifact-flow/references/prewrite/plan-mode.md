## Prewrite — plan-mode (class 1-2)

Purpose: gather minimum context for a small reversible change before drafting plan + PR description.

### Required inputs (block until answered)

1. **File(s) touched** — which exact paths? (grep first if user names a symbol; confirm before assuming).
2. **Behavior change (1 sentence)** — what is different after the fix? (recommended: "Before: X. After: Y.").
3. **Regression risk surface** — other callers / shared state / cross-file references? (default: grep for callers; surface count).
4. **Test plan** — existing test covers this, or new test needed? (options: extend existing / add new / manual-only with reason).
5. **Recurring-skill check** — is the touched file a recurring skill or agent SOP? If yes, a one-line status-block entry is load-bearing even for class-2 (see `references/selector.md` recurring-skill caveat).

### Best-practice references

- Rule pack: `concrete-action-verbs`, `edge-case-coverage` (in the verify-suite `/verify` rule pack).
- Guidance: grep for the canonical change before declaring a fix landed.
- Sibling SOP: `/verify` for post-implementation behavioral confirmation.

### Anti-patterns to flag during prewrite

- Scope creep into refactor (rename + cleanup + fix in one PR) — split.
- Adding features beyond the fix — surface as wishlist, not in-scope.
- Writing a spec folder for a 1-line change — escalate to class 4 only if a one-way-door decision surfaces.

### Output (writer consumes)

- `files_touched`: list[str]
- `behavior_change`: str (before/after)
- `regression_surface`: list[str] (caller paths) + risk level (low/med/high)
- `test_plan`: {kind: existing/new/manual, target: str}
- `recurring_skill`: bool (drives status-block requirement)
