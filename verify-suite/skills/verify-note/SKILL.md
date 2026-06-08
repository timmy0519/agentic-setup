---
name: verify-note
description: "[orchestrator] Use after research to run two checks on a research note: (1) verify-format — format checklist compliance, (2) verify-content — depth and completeness review that automatically expands thin sections using sonar-pro. Not a fact-checker — Perplexity is trusted. Goal is to ensure the note builds intuition. Do NOT invoke on bare \"verify\" without context — that's ambiguous with verify-spec."
---

## I/O Contract

**Input**: path to a research note — e.g. `Research/topic.md`

**Parameters**:

| Name | Source | Type | Default | Valid values | Required |
|------|--------|------|---------|--------------|----------|
| note_path | user message or argument | file path string | — | any `.md` file path under `Research/` | yes |

No optional parameters are accepted.

**Output**:
- FORMAT OK or itemized list of format failures (from verify-format)
- Content expansion report: sections expanded, flags raised, items deferred to task.md (from verify-content)
- Note file updated in-place (by verify-content)

**Second-run behavior**: re-runs all stages from scratch on the same note; format check is idempotent; content check re-evaluates current state of note; no state carryover between runs

## Subagents

| Subagent | Type | Receives | Produces | Stage |
|----------|------|----------|---------|-------|
| verify-format | atomic | absolute note_path | FORMAT OK or itemized list of format violations | Stage 2 |
| verify-content | orchestrator | absolute note_path | Expansion report: sections expanded, flags raised, items deferred; note mutated in-place | Stage 4 |

## Execution

Run the verification workflow defined in `references/sop.md`.
