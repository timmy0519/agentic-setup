# Verify Spec SOP (Orchestrator)

## Overview

Skill type: Orchestrator

Purpose: verify the structural integrity of a spec folder by dispatching dedicated leaf verifiers against each spec file present and consolidating their verdicts.

Pipeline shape: sequential per-file dispatch — Steps 1 and 2 execute inline; Steps 3, 4, and 5 each dispatch one subagent (conditioned on file presence); Step 6 aggregates inline.

Leaf skills are dispatched as subagents that inline-execute their own SOP. These are NOT Skill tool calls. Orchestrators dispatching atomics internally bypass atomic-runner.

Negative triggers:
- Do not use to verify a single spec file — invoke the leaf skill directly (verify-requirements, verify-design, or verify-task).
- Do not use to write or author a spec — use spec-authoring.

---

## Parameters

| Name | Source | Type | Default | Valid values | Required |
|------|--------|------|---------|--------------|----------|
| spec_folder | user message or argument | directory path string | — | any path whose directory contains at least one of requirements.md, design.md, task.md | yes |

Path resolution: accept vault-relative paths (e.g. `Projects/foo/specs/bar`); resolve to absolute before dispatching to subagents.

Implicit parameters (not user-supplied):
- Leaf SOP paths: `${CLAUDE_PLUGIN_ROOT}/skills/verify-requirements/references/sop.md`, `${CLAUDE_PLUGIN_ROOT}/skills/verify-design/references/sop.md`, `${CLAUDE_PLUGIN_ROOT}/skills/verify-task/references/sop.md` — read by each subagent at dispatch time; hardcoded, not parameterized.

---

## Subagent Contracts

### verify-requirements-runner

- Invoked at: Step 3
- Receives: absolute path to `{spec_folder}/requirements.md`
- Produces: `[PASS]` or `[FAIL] requirements.md — <violation list>`

### verify-design-runner

- Invoked at: Step 4
- Receives: absolute path to `{spec_folder}/design.md`; absolute path to `{spec_folder}/requirements.md` (cross-reference — pass even if absent; subagent handles missing gracefully)
- Produces: `[PASS]` or `[FAIL] design.md — <violation list>`

### verify-task-runner

- Invoked at: Step 5
- Receives: absolute path to `{spec_folder}/task.md`; absolute path to `{spec_folder}/design.md` (cross-reference — pass even if absent; subagent handles missing gracefully)
- Produces: `[PASS]` or `[FAIL] task.md — <violation list>`

Emit all subagent outputs verbatim. Do not suppress or reformat FAIL output.

---

## Validator Coverage

Leaf verifiers (verify-requirements-runner, verify-design-runner, verify-task-runner) are the external validators. The orchestrator consumes their verdicts without modification — no self-grading.

Cross-reads (verify-design reads requirements.md; verify-task reads design.md): retrieval only — low-risk idempotent, no validator needed.

---

## User Gates

No user gate — all operations are read-only; no file is modified.

---

## Repair Loops

No repair loop — verdict is consumed by the user, not by the orchestrator. User takes action (edit files, re-run) outside this skill.

If any leaf returns empty output (not PASS, not FAIL): retry once with the same inputs. If still empty, record as ERROR for that file in the summary and continue with remaining files.

---

## Step 1 — Folder Check

Goal: confirm spec_folder exists before dispatching any subagent.
Dispatch: inline.

- Resolve `{spec_folder}` to an absolute path.
- If the path does not exist as a directory: emit `[ERROR] Spec folder not found: {spec_folder}` and stop.

---

## Step 2 — File Presence Check

Goal: determine which spec files are present; set per-file PRESENT/MISSING state.
Dispatch: inline.

- Check for `{spec_folder}/requirements.md`. Record PRESENT or MISSING.
- Check for `{spec_folder}/design.md`. Record PRESENT or MISSING.
- Check for `{spec_folder}/task.md`. Record PRESENT or MISSING.

For each MISSING file: emit `[WARN] <file> not found — skipped`.

If all three files are MISSING: emit three `[WARN]` lines then abort with `[ERROR] No spec files found at {spec_folder}`.

---

## Step 3 — verify-requirements-runner

Goal: verify structural integrity of requirements.md.
Dispatch: Agent dispatch — verify-requirements-runner (atomic).

Condition: run only if requirements.md is PRESENT.

The subagent reads and executes the SOP at `${CLAUDE_PLUGIN_ROOT}/skills/verify-requirements/references/sop.md` inline. This is not a Skill tool call.

Subagent receives: absolute path to `{spec_folder}/requirements.md`.

Subagent produces: `[PASS]` or `[FAIL] requirements.md — <violation list>`.

Emit the subagent result verbatim.

---

## Step 4 — verify-design-runner

Goal: verify structural integrity of design.md and coverage against requirements.md.
Dispatch: Agent dispatch — verify-design-runner (atomic).

Condition: run only if design.md is PRESENT.

The subagent reads and executes the SOP at `${CLAUDE_PLUGIN_ROOT}/skills/verify-design/references/sop.md` inline. This is not a Skill tool call.

Subagent receives: absolute path to `{spec_folder}/design.md`; absolute path to `{spec_folder}/requirements.md` (cross-reference; subagent handles absent gracefully).

Subagent produces: `[PASS]` or `[FAIL] design.md — <violation list>`.

Emit the subagent result verbatim.

---

## Step 5 — verify-task-runner

Goal: verify structural integrity of task.md and coverage against design.md.
Dispatch: Agent dispatch — verify-task-runner (atomic).

Condition: run only if task.md is PRESENT.

The subagent reads and executes the SOP at `${CLAUDE_PLUGIN_ROOT}/skills/verify-task/references/sop.md` inline. This is not a Skill tool call.

Subagent receives: absolute path to `{spec_folder}/task.md`; absolute path to `{spec_folder}/design.md` (cross-reference; subagent handles absent gracefully).

Subagent produces: `[PASS]` or `[FAIL] task.md — <violation list>`.

Emit the subagent result verbatim.

---

## Step 6 — Summary

Goal: aggregate per-file verdicts into a consolidated report.
Dispatch: inline.

Emit in this exact format:

```
{spec_folder} — {N} files checked, {N_PASS} PASS, {N_FAIL} FAIL

<if all checked files pass>
SPEC OK

<if any checked file fails>
Failures:
- requirements.md: <violation list>   (omit if PASS or skipped)
- design.md: <violation list>         (omit if PASS or skipped)
- task.md: <violation list>           (omit if PASS or skipped)
```

Count only files that were checked (PRESENT, not skipped) in the totals. Files recorded as ERROR count as FAIL in the totals.

---

## Failure Handling

| Scenario | Trigger | Action | Escalation |
|----------|---------|--------|------------|
| spec_folder not found | path does not exist as a directory | abort; emit `[ERROR] Spec folder not found: {spec_folder}`; suggest the user verify the path | — |
| All 3 files missing | none of requirements.md / design.md / task.md present | emit three `[WARN]` lines; abort with `[ERROR] No spec files found at {spec_folder}` | — |
| Leaf returns empty output | subagent produces no PASS and no FAIL | retry once with the same inputs | Still empty → record as ERROR in summary; continue with other files |
| Leaf SOP not found | skill file missing or unreadable | surface error; skip that file; mark as SKIPPED in summary | — |

---

## Second-Run Behavior

Second run produces the same result as first run given the same file contents. All operations are read-only; no state changes between runs.

| Mode | Expected output |
|------|----------------|
| Re-run, files unchanged | Identical to first run |
| Re-run after user edits a file | Previously failing files now PASS if the violations were resolved |
| Re-run with `--mode` variants | N/A — no mode variants exist |
