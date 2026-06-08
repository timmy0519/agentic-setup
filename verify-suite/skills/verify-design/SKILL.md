---
name: verify-design
description: "[atomic] Use to check a design.md file against the structural checklist and verify it satisfies all requirements — diagram present, decisions have rationale, file/path inventory, no user stories, no vague language, every requirement and in-scope item addressed. Reads requirements.md from the same folder if present. Called by /verify-spec or standalone when only design.md has changed."
---

## I/O Contract

**Inputs:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | absolute path | yes | Path to the `design.md` file to verify (e.g. `Projects/foo/specs/design.md`) |
| `requirements.md` | derived | no | Auto-loaded from the same folder as `file_path` if present; never supplied by caller |

**Output:**

- Inline text report — no file written
- Structure:
  - `[FAIL] — <description>` for each failed check, grouped at top
  - `[PASS] <check name>` for each passing check
  - `[NOTE] — requirements.md not found; coverage check skipped` if companion file absent
  - `DESIGN OK` appended only if all checks pass

**Output schema types:**

| Field | Type |
|-------|------|
| `check_result` | enum: `[PASS]` \| `[FAIL]` \| `[NOTE]` |
| `structural_checks` | 17 fixed checks: diagram present, E2E sequence coverage, decisions have rationale, file/path inventory, no user stories, no vague language, no convention-as-design, SSOT sync, OCP (pattern not enumeration), DRY (don't fetch what you have), no contradiction, namespace governance, tradeoff explicitness, assumption fragility, contract stability, parallel branch data dependency, concurrent execution consistency |
| `coverage_checks` | per user story + per in-scope item from `requirements.md` (count varies; omitted if file absent) |
| `verdict` | string: `"DESIGN OK"` \| absent |

**Second-run behavior:** Deterministic and idempotent — identical input produces identical output on every run.

## Trigger Phrases

- "verify this design"
- "check design.md"
- "run verify-design on ..."
- "check the design file"
- "verify design for ..."
- called internally by `/verify-spec` with a file path argument

## What It Does

1. Loads the design.md file at the provided path; stops with an error if not found
2. Derives the requirements.md path (same folder, filename `requirements.md`) and reads it if present
3. Runs 17 structural checks: diagram present, E2E sequence coverage, decisions have rationale, file/path inventory, no user stories, no vague language, no convention-as-design, SSOT sync, OCP, DRY, no contradiction, namespace governance, tradeoff explicitness, assumption fragility, contract stability, parallel branch data dependency, concurrent execution consistency
4. Runs requirements coverage check if requirements.md was found (every user story and every in-scope item must appear in the design)
5. Outputs the report — failures grouped first, then passes, `DESIGN OK` if all pass

## What It Does NOT Do

- Check content quality or suggest improvements
- Access the web or call external tools
- Create or modify any files
- Check task.md or any file other than design.md and requirements.md

## Routing Boundaries

| If the user wants... | Use instead |
|---------------------|-------------|
| Verify all spec files (requirements, design, task) | `/verify-spec` |
| Verify requirements.md structure and completeness | `/verify-requirements` |
| Verify task.md structure and completeness | `/verify-task` |
| Check a research note formatting | `/verify-format` |
| Write or improve a design | `/spec-authoring` |

## Invocation

Run the verification workflow defined in `references/sop.md`.
