## Prewrite — requirements.md (class 4+)

Purpose: gather user-value framing before drafting requirements. PM-tier only — no mechanism.

### Required inputs (block until answered)

1. **User (audience for the feature, not the doc)** — who has the unmet need? (role + context).
2. **Candidate user stories** — decompose vague comments into testable stories; confirm each with the user before writing (ground inputs before committing them to a spec).
3. **Must-have vs nice-to-have filter** — nice-to-haves go to `WISHLIST.md`, not into the spec. Requirements hold the user-value bar (no mechanism).
4. **Three scope categories** — (a) in-this-doc, (b) deferred to later phases (still in-scope work), (c) excluded entirely. Don't collapse (b) and (c).
5. **Altitude tier** — user-story tier (user value) / system-mechanism tier (subsystems must exist) / impl tier (explicitly out of scope).
6. **Acceptance signal** — how will the user know the feature is delivered? (testable, per user story).

### Best-practice references

- Rule pack: `user-story-testability`, `decisions-justified`, `requirements-format` (in the verify-suite `/verify` rule pack).
- Sibling SOP: `/spec-authoring` (heavy alternative — kept for backward compat).

### Anti-patterns to flag during prewrite

- Mechanism leakage (writing how, not what) — that's design.md's job.
- Listing nice-to-haves as in-scope — push to WISHLIST.md.
- Extrapolating vague user comments into user stories without confirmation.
- Collapsing deferred and excluded scope into a single "out of scope" bucket.

### Output (writer consumes)

- `audience`: str (feature user)
- `user_stories`: list[{story: str, acceptance: str}]
- `in_scope`: list[str]
- `deferred`: list[str]
- `excluded`: list[str]
- `altitude_tier`: user-story | system-mechanism (impl excluded by default)
