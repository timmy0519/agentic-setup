---
name: verify-task
description: "[atomic] Check a task.md file against structural requirements (checkbox format, open questions section, deferred items separated, no completed items, concrete action verbs) and verify coverage against design.md (every file in inventory and major flow component has a corresponding task). Return a PASS with no output or FAIL with a detailed violation report. No design.md = skip design coverage, proceed with structural checks only."
---

## I/O Contract

**Inputs:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `input_file` | absolute path | yes | Absolute path to the task.md file to verify |
| `design.md` | derived | no | Auto-loaded from same folder as `input_file`; if absent, design coverage check is skipped |
| `requirements.md` | derived | no | Auto-loaded from same folder as `input_file`; if absent, requirements-verification task check is skipped |

**Output:**

- On PASS: single line `TASK OK`
- On PASS with skipped check: `TASK OK (design.md not found — coverage check skipped)`
- On FAIL: one `[FAIL] — <violation description and location>` line per violation, ending with `TOTAL FAILURES: [count]`
- On fatal input error: single line `[FAIL] — <reason>`

**Output schema types:**
- `verdict`: enum — `"TASK OK"` | `"FAIL"`
- `failure_line`: format string — `[FAIL] — <description>`

**Second-run behavior:** Deterministic — same input file produces identical output on every run.

## Trigger Phrases

- "verify this task file"
- "check task.md"
- "run verify-task on ..."
- "verify tasks for ..."
- Internal callers: `verify-spec` (full spec folder verification), `spec-authoring` (post-write structural check)

## What It Does

1. Validates `input_file` path — fails fast if file not found or path is a directory
2. Auto-loads companion files (`design.md`, `requirements.md`) from the same folder; notes any that are absent
3. Runs 5 structural checks on task.md: checkbox format, open questions section, deferred items separation, no completed items, concrete action verbs
4. If `requirements.md` loaded: checks that the last item in the Immediate section is a requirements-verification task
5. If `design.md` loaded: checks that every file marked Create/Edit in the file inventory and every major flow component has a corresponding task
6. Aggregates all failures and outputs `TASK OK` or the full violation report with `TOTAL FAILURES: [count]`

## What It Does NOT Do

- Fix or modify any file
- Access the web or external sources
- Evaluate whether tasks are correct, complete, or well-scoped (structural checks only)
- Check any spec file other than task.md and its auto-derived companions
- Spawn subagents

## Routing Boundaries

| If the user wants... | Use instead |
|---------------------|-------------|
| Verify all spec files in a folder | `verify-spec` |
| Verify requirements.md | `verify-requirements` |
| Verify design.md | `verify-design` |
| Write or scaffold a task.md | `spec-authoring` |
| Check a research note format | `verify-format` |

## Invocation

Run the verification workflow defined in `references/sop.md`.
