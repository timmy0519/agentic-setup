## Artifact-flow SOP

Thin orchestrator. Three stages: classify → per-artifact loop → close.

## Stage 1 — Classify

Determine task class (1-7) using `references/selector.md`.

- If `{class_hint}` provided: validate against task description; if mismatch, present both options + recommended + reasoning, ask user.
- If not provided: examine task wording for signals (scope, stakeholder count, reversibility), pick class, **state the verdict + 1-line reasoning** before proceeding.

Output: `{class}` + `{artifact_set}` (from selector).

## Stage 2 — Per-artifact loop

For each artifact in `{artifact_set}`, in order:

### 2a. Prewrite gather (Agent dispatch → prewrite-gatherer)

Dispatch prewrite-gatherer with: `{doctype}`, `{task}`, `references/prewrite/{doctype}.md` (absolute path).

Prewrite-gatherer steps:
1. Read the prewrite ref for this doctype.
2. Identify which prewrite questions are answerable from existing context (prior artifacts in this run, vault docs, prior conversation).
3. Surface only **unanswered** questions to user as multi-option clarify (2-4 concrete options + recommendation).
4. Wait for response. Re-prompt once on ambiguous.
5. Return: structured answers dict + which were inferred vs user-confirmed.

### 2b. Write (Agent dispatch → writer)

Dispatch writer with: `{doctype}`, prewrite answers, `/verify` rule pack path, prior artifacts in this run (paths).

Writer steps:
1. Read the relevant rule pack rules for this doctype:
   - `general/serves-reader-purpose.md` (always)
   - `structural/{doctype}-format.md` (if exists)
   - Any doctype-specific general rules (see selector → rules map)
2. Draft artifact in target location. Apply rules during drafting (not after).
3. Self-grep for known leak patterns (`round 1`, `synthesis-writer`, etc — see `serves-reader-purpose` Tier 3).
4. Return: artifact path + 1-line summary of what's in it.

### 2c. Review (Agent dispatch → reviewer)

Dispatch reviewer with: artifact path, `/verify` rule pack path, prior artifacts (for cross-ref).

**Pick review depth before dispatch:**
- **Default — checklist reviewer:** apply `/verify` rules in tier order. Right for routine gates.
- **Consequential gate → adversarial reviewer:** when the gate carries tradeoffs, is open-ended, is use-case-dependent, risks over-engineering, or is a one-way door (selector class 6–7), dispatch the `adversarial-reviewer` agent instead of (or after) the checklist pass. Record which depth ran as the gate's review evidence in task-tool.

Reviewer steps:
1. Apply rules in tier order (Tier 1 first per `serves-reader-purpose`); adversarial reviewer red-teams intent per its own method.
2. Return verdict (SHIP / REWRITE-NEEDED) + line-anchored fixes.

Retry contract (max 2):
- PASS → advance to 2d.
- REWRITE-NEEDED + retries left → re-dispatch writer with reviewer's fix list; re-run 2c.
- REWRITE-NEEDED + retries exhausted → surface to user: continue with known fails / fix manually / abort.

### 2d. Brief user (progressive disclosure)

Surface to user in this shape (≤6 lines):
```
✓ {doctype} written: {path}
TL;DR: {1-sentence takeaway}
Decisions made: {decision-1}, {decision-2}
Open: {any deferred question}
Next: {next artifact in set, or "done"}
Continue? (yes / redirect / show me)
```

Wait for user response. Default = continue. On "redirect": ask what to change, re-run 2a-c. On "show me": dump full artifact to terminal + wait for continue.

After last artifact, advance to Stage 3.

## Stage 3 — Close

1. Status block: list each artifact + verdict + reviewer-found-issues-count.
2. If research note: update `Research/_index.md`.
3. If spec: ensure `Projects/<proj>/index.md` references the spec folder.
4. Return summary: artifacts shipped + open questions + next-step suggestion.

## Failure handling

- Prewrite-gatherer surfaces unanswerable question (no recommended default) → escalate to lead/user immediately; do not proceed.
- Writer can't satisfy a rule (e.g., grounding source missing) → return partial draft with explicit gap; reviewer flags as FAIL; retry consumes the gap as constraint.
- Reviewer rule conflict (two rules contradict) → surface to user; do not auto-resolve.

## Negative triggers

- Verify-only on existing artifact → use `/verify` directly.
- Single-file edit of existing artifact → don't invoke this skill.
- Class-3 research → delegate to `/research-team` (it has its own thin SOP).
- Heavy spec authoring with decision-grounding gates → use `/spec-authoring` (kept for backward compat).
