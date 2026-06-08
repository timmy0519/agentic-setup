# Verify Research Output SOP (Orchestrator)

## Overview

**Skill type**: Orchestrator

**Purpose**: Sequence two verification checks on a research note — format compliance first, then depth expansion — and surface a combined result.

**Pipeline shape**: Linear, 5-stage. Stage 1 (inline pre-flight) → Stage 2 (Agent dispatch → verify-format) → Stage 3 (User gate) → Stage 4 (Agent dispatch → verify-content) → Stage 5 (inline report). One user gate between Stages 2 and 3.

**Negative triggers**:
- Do NOT invoke for spec files — use verify-spec instead
- Do NOT invoke when the user wants only format checking — use verify-format standalone
- Do NOT invoke when the user wants only content checking — use verify-content standalone
- Do NOT invoke on a bare "verify" without note context — that is ambiguous with verify-spec

---

## Parameters

| Name | Source | Type | Default | Valid values | Required |
|------|--------|------|---------|--------------|----------|
| note_path | user message or argument | file path string | — | any `.md` file path under `Research/` | yes |

No optional parameters are accepted. `--skip-format` and `--skip-content` flags are not supported.

---

## Subagent Contracts

### verify-format
- **Invoked at**: Stage 2
- **Receives**: absolute `note_path`
- **Produces**: `FORMAT OK` or an itemized list of format violations (one per line)
- **Type**: atomic

### verify-content
- **Invoked at**: Stage 4
- **Receives**: absolute `note_path`
- **Produces**: expansion report (sections expanded, flags raised, items deferred to task.md) + note mutated in-place at `note_path`
- **Type**: orchestrator — verify-content dispatches its own internal subagents (Section Depth Evaluator, Section Expander, Source Validator, Requirements Coverage Checker); their contracts are out of scope for this SOP; treat verify-content as a black box with the above contract
- **Invocation method**: Agent dispatch — do NOT nest subagents inside verify-content's invocation

---

## Stage 1 — Pre-flight check [inline]

**Goal**: confirm `note_path` exists before dispatching any subagent.

Check that the file at `note_path` exists on disk.

- If file does not exist: abort. Tell the user — "Note not found at `{note_path}`. Check the path and verify the file is under `Research/`." Do not dispatch verify-format or verify-content.
- If file exists: proceed to Stage 2.

---

## Stage 2 — Format Check [Agent dispatch → verify-format subagent]

**Goal**: run format compliance check and surface the result.

**Dispatch**: invoke verify-format as an Agent subagent with exactly:
- `note_path`

verify-format produces: `FORMAT OK` or an itemized list of format failures (one line per failure).

Surface the format result to the user immediately after verify-format returns.

**Repair loop**: if verify-format returns empty output (no `FORMAT OK` and no failure list), retry once with the same `note_path`. If still empty after retry, surface to the user: "verify-format returned no output for `{note_path}` after two attempts (Stage 2)." Offer: retry again or abort. Do not proceed to Stage 3 until verify-format produces a result.

Proceed to Stage 3.

**Validator note**: Stage 3 (user gate) is the explicit validator for this stage's output — the user reviews the format result and confirms routing before the pipeline continues. This is the inline gate evaluation step.

---

## Stage 3 — User gate [User gate]

**Goal**: give the user visibility into the format result and confirm before content check proceeds (which will mutate the note in-place).

**Skip this gate only if verify-format returned `FORMAT OK` and no format failures were listed. Proceed directly to Stage 4.**

If format failures are present, present the following gate:

1. **What exists today**: format check complete — failures detected (list each one)
2. **Before → After**: proceeding will dispatch verify-content, which may mutate the note in-place by expanding thin sections; the note file will be changed on disk
3. **Why**: content check mutates the file; user should confirm before a write occurs
4. **Default**: select A (proceed) if format result is `FORMAT OK`; select B (fix format first) if format violations are present.
5. **Options**:
   - **(A) Proceed to content check** — dispatch verify-content now (default if FORMAT OK)
   - **(B) Fix format violations first** — stop here; fix violations manually using the list above, then re-invoke `/verify-note {note_path}`; do not run verify-format standalone first — re-invoking verify-note re-runs the full pipeline from scratch
   - **(C) Skip content check and exit** — stop here; report format result only; no note mutation

On option A: proceed to Stage 4.
On option B: stop. Do not dispatch verify-content. Output the format failure list. Inform user to fix and re-invoke.
On option C: stop. Do not dispatch verify-content. Proceed to Stage 5 with only the format result.

---

## Stage 4 — Content Check [Agent dispatch → verify-content subagent]

**Goal**: run depth expansion check and mutate the note in-place.

**Dispatch**: invoke verify-content as an Agent subagent with exactly:
- `note_path`

verify-content produces: expansion report (sections expanded, flags raised, items deferred to task.md) + note file mutated in-place.

Note: verify-content is itself an orchestrator. Invoke it via Agent dispatch only — do not attempt to nest or inline its internal steps.

**Repair loop**: if verify-content returns empty output (no expansion report and no indication of completion), retry once with the same `note_path`. If still empty after retry, surface to the user: "verify-content returned no output for `{note_path}` after two attempts (Stage 4)." Offer: retry again or abort. Do not proceed to Stage 5 until verify-content produces a result or user chooses to abort.

**Post-check (inline — orchestrator reads verify-content output):**
- Receives: verify-content's returned report
- Checks:
  - Whether any unresolved TODO markers are present in verify-content's output
  - Whether any flags were left unresolved (hit retry cap without clearing)
- Produces: `{unresolved_items}` list — collect all unresolved TODOs and uncapped flags found; pass this list to Stage 5

Proceed to Stage 5.

**Validator note**: the user gate at Stage 3 is the pre-write external control for this stage — consent before note mutation. The inline post-check above (Stage 4b) is the post-write external control — orchestrator reads verify-content's returned report for unresolved items. verify-content's internal subagents handle section-level validation internally.

---

## Stage 5 — Report [inline]

**Goal**: assemble and output the combined result.

1. State the format result: `FORMAT OK` or the itemized failure list from Stage 2.
2. State the content result: expansion report from Stage 4 (sections expanded, flags resolved, items deferred). Omit if user chose option B or C at Stage 3.
3. If format failures existed and user chose option A (proceed): append — "Format issues noted above remain unresolved. Run `/verify-format {note_path}` after addressing them."
4. If user chose option C (skip content): append — "Content check skipped at user request. Re-invoke `/verify-note {note_path}` to run content check."

---

## Failure handling

| Scenario | Trigger | Action | Escalation |
|----------|---------|--------|------------|
| note_path not found | File does not exist at path | Abort; tell user path not found; suggest checking `Research/` folder | — |
| verify-format returns empty | No `FORMAT OK` and no violation list returned | Retry once with same `note_path` | Still empty → surface to user with stage and subagent info; offer retry or abort |
| verify-content returns empty | No output returned | Retry once with same `note_path` | Still empty → surface to user with stage and subagent info; offer retry or abort |
| User aborts at Stage 3 gate | User selects option B or C | Exit immediately; report format result only; no note mutation | — |

---

## Second-run behavior

Same `note_path` invoked again: re-run all stages from scratch.

- Re-reads `note_path` from disk at Stage 1 (picks up any edits made between runs)
- No state carryover between runs — verify-note stores no state
- Stage 2 re-dispatches verify-format regardless of prior run result
- Stage 4 re-dispatches verify-content regardless of prior run result (content check re-evaluates current state of note)
- No skip logic — each run is a fresh evaluation from Stage 1

Common second-run scenarios:

| Scenario | Result |
|----------|--------|
| Note unchanged since last run | Format check is idempotent — same result; content check may vary if subagent sampling differs |
| Note was expanded by verify-content on prior run | Content check re-evaluates the now-expanded note; previously THIN sections may now be SUFFICIENT |
| Format issues were fixed manually before re-run | Format check returns `FORMAT OK`; Stage 3 gate is skipped; content check proceeds without interruption |

---

## Validator coverage

| Subagent | Risk level | External validator | Rationale |
|----------|------------|-------------------|-----------|
| verify-format (Stage 2) | LOW | Inline gate evaluation at Stage 3 (user reviews format result and confirms routing) | Idempotent classification against a mechanical checklist; no note transformation; self-grading risk is low |
| verify-content (Stage 4) | HIGH | (1) User gate at Stage 3 (pre-write consent) + (2) inline post-check at Stage 4b (orchestrator reads returned report for unresolved TODOs and uncapped flags) | verify-content is validated at two levels: (1) pre-write user gate (Stage 3) — consent before mutation; (2) post-write inline post-check (Stage 4b) — orchestrator reads returned report for unresolved items; verify-content's internal subagents handle section-level validation. |
