---
name: verify-content
description: "[orchestrator] Use when a research note feels thin, sections lack intuition, or the user asks to deepen or expand a note. Checks each section builds understanding — not fact-checking. Automatically expands thin sections using sonar-pro. Called by /verify-note or invoke standalone on a specific note. Do NOT invoke on bare \"verify my note\" — that routes to /verify-note which runs both format and content checks."
---

## I/O Contract

**Input**: path to a research note — e.g. `Research/openclaw/openclaw - overview.md`

**Output**:
- The note file updated in-place with expanded sections
- An inline report to the user listing: what was expanded, what flags were raised, what was deferred to task.md
- Any unresolvable items added to task.md in the same folder (created if absent)

**Second-run behavior**: Re-read the note from disk. Re-run all depth checks from scratch. Sections previously expanded but now SUFFICIENT are skipped. Sections that were deferred to task.md on the first run are not re-expanded — they remain in task.md. The output report lists only items that changed on this run.

## Subagents

| Subagent | Type | Receives | Produces |
|----------|------|----------|---------|
| input-loader | inline | `note_path` (string) | `note_text`, `requirements_data`, `requirements_skip_reason` |
| requirements-coverage-checker | agent dispatch | `note_path` (absolute), `requirements.md` path (absolute), `requirements_data` | `{ requirement_id, requirement_text, verdict: COVERED \| UNCOVERED, evidence }` per requirement; `{ action_item, status: present \| absent }` per action item |
| requirements-coverage-validator | agent dispatch | `note_path` (absolute), `requirements.md` path, checker output (coverage verdict list) | Validated coverage list — each COVERED verdict confirmed or downgraded to UNCOVERED with reason |
| section-depth-evaluator | agent dispatch (per section) | `section_heading`, `section_body`, `note_context`; 6 depth check criteria | `{ section_name, flags: list of flag types triggered, pass: true \| false }` |
| section-expander | agent dispatch (per flag, retry loop) | `section_text`, `flag_type`, `note_path` (absolute), targeted sonar-pro query | Expanded section text written to note in-place; write confirmation returned |
| source-validator | agent dispatch | `note_path` (absolute), list of `{ claim_text, query }` pairs | `{ claim, source, verdict: VALID \| UNVERIFIABLE \| CONTRADICTED }` per claim |

## Execution

Run the full content depth workflow defined in `references/sop.md`.
