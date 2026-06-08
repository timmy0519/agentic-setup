---
name: verify-spec
description: [orchestrator] Use after writing or updating a spec folder (requirements.md, design.md, task.md) to run structural verification across all three files. Orchestrates verify-requirements, verify-design, and verify-task as leaf skills and produces a consolidated PASS/FAIL summary. Use when a spec folder has been written or updated and needs a structural review. Do not use for verifying a single spec file in isolation — use the leaf skill directly.
---

Run the verification workflow defined in `references/sop.md`.

## Arguments

- **spec_folder** (required): absolute or vault-relative path to the spec folder — e.g. `Projects/research-agent/specs/verify-spec`

## What it does

- Checks for requirements.md, design.md, and task.md in the spec folder
- Dispatches verify-requirements, verify-design, and verify-task as subagents for each present file
- Consolidates results into a single PASS/FAIL summary with SPEC OK or grouped failure list
- Emits `[WARN]` for each missing file — missing files do not abort the run

## What it does not do

- Does not verify a single spec file in isolation — use the leaf skill directly (verify-requirements, verify-design, or verify-task)
- Does not check content quality or suggest improvements
- Does not access the web or call external tools
- Does not create or modify any files

## Subagents

| Name | Type | Invoked at | Receives | Produces |
|------|------|------------|----------|----------|
| verify-requirements-runner | atomic | Step 3 | absolute path to requirements.md | `[PASS]` or `[FAIL] requirements.md — <violations>` |
| verify-design-runner | atomic | Step 4 | absolute path to design.md; absolute path to requirements.md (cross-reference, may be absent) | `[PASS]` or `[FAIL] design.md — <violations>` |
| verify-task-runner | atomic | Step 5 | absolute path to task.md; absolute path to design.md (cross-reference, may be absent) | `[PASS]` or `[FAIL] task.md — <violations>` |
