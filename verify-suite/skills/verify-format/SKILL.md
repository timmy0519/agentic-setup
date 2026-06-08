---
name: verify-format
description: "[atomic] Use after writing a research note to check format compliance — TL;DR, diagrams, footnote citations, analogy section, gap analysis visual, no code snippets, task.md exists. No web calls. Called by /verify-note or invoke standalone on a specific note path. Do NOT invoke on bare \"verify my note\" — that routes to /verify-note which runs both format and content checks."
---

## I/O Contract

**Inputs:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `input_note` | file path | yes | Absolute or vault-relative path to the research note to check (e.g. `Research/topic/topic.md`) |
| `references/design.md` | implicit | no | Format checklist; auto-loaded by the SOP on every invocation; not provided by the caller |

**Output:**

- Delivery: inline text report printed to the conversation (no files written)
- Structure:
  1. **Failures section** — all `[FAIL]` lines first; "No failures." if none
  2. **All checks** — every check result in table order: `[PASS]` or `[FAIL] — <detail>`
  3. **Verdict line** — `FORMAT OK` or `FORMAT FAIL — N check(s) failed`
- 10 checks applied: TL;DR, Diagram in Key findings, Competitor section trimmed, Competitor has diagram, Gap analysis has visual, Analogy section, No inline citations, Footnotes at bottom, No code snippets, task.md exists

**Output schema types:**
- `check_result`: enum — `[PASS]` | `[FAIL]`
- `verdict`: enum — `"FORMAT OK"` | `"FORMAT FAIL — N check(s) failed"`

**Second-run behavior:** Fresh report each run — no state persisted between invocations.

## Trigger Phrases

- "check the format of [note]"
- "verify format [note path]"
- "format check [note]"
- "does [note] pass format?"
- `/verify-format [path]`

Do NOT trigger for:
- "verify my note" (bare, no path) → routes to `/verify-note`
- "check the content of [note]" → routes to `/verify-content`
- "verify this spec" / "check requirements.md" → routes to spec verify skills

## What It Does

1. Loads `references/design.md` (the format checklist) and the target note
2. Applies each of the 10 checks mechanically against the note content
3. Outputs a structured inline report: failures grouped first, all check results in table order, then verdict

## What It Does NOT Do

- Check content quality, depth, or insight density — that is `/verify-content`
- Make web calls or external searches
- Write any files or persist state between runs
- Spawn subagents
- Run content or requirements checks — format compliance only

## Routing Boundaries

| If the user wants... | Use instead |
|---------------------|-------------|
| Check content depth, insight density, or analogy quality | `/verify-content` |
| Verify both format and content together | `/verify-note` |
| Verify a requirements spec file | `/verify-requirements` |
| Verify a design spec file | `/verify-design` |
| Verify a task spec file | `/verify-task` |

## Invocation

Run the format verification workflow defined in `references/sop.md`.
