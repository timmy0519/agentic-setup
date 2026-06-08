# Verify Format SOP

## Overview

Check a research note against the format checklist defined in `references/design.md`. Atomic — no subagents. All steps execute in the main agent context. No web calls.

Output: an inline pass/fail report printed to the conversation. Each check gets one line. Failures are grouped first. If all checks pass, print `FORMAT OK`. Use this skill after writing a research note, or when `/verify` dispatches it as a subagent.

When to use this vs `/verify`: use this skill when you only want the format check. Use `/verify` when you want both format and content checks together.

## Parameters

- **input_note** (required, file path): absolute or vault-relative path to the research note to check (e.g. `Research/topic/topic.md`)
- **Implicit dependency**: `references/design.md` — the format checklist, loaded by this SOP. Not provided by the user.

If `input_note` is not provided: stop and report "No note path given — provide the path to the note."

## Second-run behavior

Re-running on the same note after edits produces a fresh report. No state is persisted between runs. All checks are re-evaluated from the current file contents on every invocation.

## Steps

### Step 1 — Load inputs

1. Resolve `references/design.md` to an absolute path and read it.
   - If file does not exist: stop and report "references/design.md not found — cannot run format check."
2. Resolve `{input_note}` to an absolute path and read it.
   - If path cannot be resolved or file does not exist: stop and report "Note not found: {input_note}"
   - If file exists but is empty: do not stop — proceed with all checks; empty note will fail every check.

### Step 2 — Apply each check

For each row in the table below: apply the pass condition to the note content; record `[PASS]` or `[FAIL] — <what is wrong and where in the note>`.

| Check | Pass condition |
|-------|---------------|
| TL;DR | First section is a blockquote or bold 2–3 sentence summary |
| Diagram in Key findings | A Mermaid fenced code block (` ```mermaid `) appears before or within the Key findings section |
| Competitor section trimmed | No niche or low-adoption tools included in any comparison section |
| Competitor has diagram | A Mermaid fenced code block appears in the competitor/comparison section |
| Gap analysis has visual | A Mermaid fenced code block or other visual element appears before the gap list |
| Analogy section | An analogy section exists anywhere in the note |
| No inline citations | No `[1]`, `[2]` style inline numbers — only `[^n]` footnote syntax |
| Footnotes at bottom | `[^n]:` definitions exist in a Sources section at the bottom |
| No code snippets | No triple-backtick code blocks other than Mermaid (` ```mermaid `) blocks |
| task.md exists | A `task.md` file exists in the same folder as the note (e.g. `Research/topic/task.md`) |

**Note on Mermaid check**: only count a real fenced code block (triple backticks with `mermaid` label on its own line). Do not count inline code spans or mentions of "mermaid" in prose.

**Note on task.md check**: this check assumes folder layout (`Research/<topic>/<topic>.md`). If the note is stored flat (`Research/topic.md`), note this explicitly in the report rather than failing silently.

### Step 3 — Output the report

Print the report inline in this order:

1. **Failures section** — list all `[FAIL]` lines first, one per line. If none: write "No failures."
2. **All checks** — list every check result in table order: `[PASS]` or `[FAIL] — <detail>`
3. **Verdict** — final line:
   - If all checks passed: `FORMAT OK`
   - If any checks failed: `FORMAT FAIL — N check(s) failed` (where N is the count)

## Failure handling

All failure handling is in Step 1. No other steps produce stoppable errors.

- `references/design.md` missing → stop, report error
- Note path unresolvable or file missing → stop, report error with path given
- Note empty → proceed, all checks will fail

Do not produce silent passes. If uncertain whether a check passes, record it as `[FAIL]` with the specific uncertainty noted.
