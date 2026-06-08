# Verify Design SOP

## Overview

Check a design.md file against the structural checklist and verify it satisfies all requirements. Output a pass/fail report and list every violation. The goal is to keep design docs concrete — and ensure nothing from requirements is silently dropped.

This is an atomic skill — no subagents, no web calls, no spawning. All checks are performed inline by the invoking agent.

## Parameters

- **Input file** (required): path to design.md supplied by the caller
  - Standalone invocation: user provides path as argument (e.g. `Projects/foo/specs/design.md`)
  - Called by `/verify-spec`: file path passed by the orchestrator

## Steps

1. **Load files**
   - Read the input file at the provided path
   - Derive requirements path: same folder as input file, filename `requirements.md`
   - If the input file does not exist: output `{input_file} not found — cannot run verification.` and stop
   - Read requirements.md if it exists — used for coverage check in step 3; if absent, note it and skip step 3

2. **Run structural checks**

   | Check | Pass condition |
   |-------|---------------|
   | Flow or architecture diagram | At least one Mermaid diagram block is present in the file |
   | E2E workflow coverage | For each distinct user story or use case: locate at least one diagram that shows all steps end-to-end in sequence — inputs, outputs, and decision points visible. A component or architecture diagram alone does not satisfy this. If multiple use cases exist, each requires its own sequence or flow diagram. |
   | Decisions have rationale | Every choice stated in the form "we use X" or "X not Y" has an inline reason explaining why — not just the choice |
   | File/path inventory | At least one list of concrete file paths for files to be created or modified is present in the doc |
   | No user stories | No "As a user, I want…" language — those belong in requirements.md |
   | No vague language | None of the following appear: "we should consider", "maybe", "could be", "might" — design decisions are stated as made, not tentative |
   | No convention-as-design | None of the following phrases appear: "remember to", "users should", "run this after", "periodically check" — every recurring action must have a concrete mechanism: a state signal the system detects, a checklist step owned by a named process, or an artifact that self-describes its staleness |
   | Who keeps the list up to date? | If the design creates a centralized artifact that describes other things (registry, table, config section) — verify it addresses how the artifact stays in sync when those things change. If someone has to remember to update it, flag it. (SSOT / ATAM modifiability) |
   | Do you edit the rule when adding a new thing? | If the design includes rules, config, or dispatch logic — verify they work by pattern (matching labels, scanning descriptions) not by enumerating specific instances by name. Rules that list names require editing when new instances are added. (OCP) |
   | Don't fetch what you already have | If the design proposes reading or fetching data — verify the data isn't already available through an existing mechanism (already loaded in context, already computed, already stored in a loaded artifact). (DRY / efficiency) |
   | Design doesn't contradict itself | For each constraint in requirements.md — verify the design does not introduce a mechanism that violates it. "Zero file reads" + a file read = contradiction, not a tradeoff. (SEI AD review conformance) |
   | Named things need collision rules | If the design introduces named identifiers (type labels, keywords, enum values) — verify it specifies naming constraints and collision prevention. Who enforces uniqueness? What prevents synonyms? (Namespace governance) |
   | What did you give up? | Every design decision that claims a benefit — verify it also states the tradeoff (what becomes harder, more complex, or less flexible as a result). Decisions listing only upsides are hiding downsides. (ATAM trade-off analysis) |
   | What breaks if this stops being true? | If the design lists assumptions — verify each one states what happens if it becomes false and how hard recovery is. Unlisted or unqualified assumptions are the ones that surprise you. (Assumption dependency analysis) |
   | Can this change without breaking consumers? | For every interface or contract the design exposes — verify the design addresses what happens when the interface needs to evolve. If evolution breaks all consumers, flag it. (Contract stability / backward compatibility) |
   | Parallel branch data dependency | For each pair of parallel branches in a data flow diagram that share an input: if one branch produces a filtered, transformed, or reduced version of that input, and another branch computes an aggregate, count, or threshold over items from the same input — the design must either (a) show the filtering branch as upstream of the aggregating branch, or (b) explicitly state that the two operate on independent subsets and explain why overlap is impossible. (DFD derived data rule / Yourdon-DeMarco) |
   | Concurrent execution consistent with data dependencies | For each group of steps the design marks as concurrent or parallel: verify no step in the group depends on the output of another step in the same group (for the data paths described in this design). If a dependency exists, the design must state execution order explicitly. (SEI AD review — concurrent component check) |
   | Irreversible-action scenario walkthrough | For each in-scope item that triggers an irreversible action (delete, remove, graduate, overwrite, purge): construct a scenario where all stated trigger criteria are satisfied but the original problem recurs. If the scenario is plausible, the criteria are necessary but not sufficient — flag as insufficient. Example: "Rule exists → graduate lesson" fails because "rule exists, same error occurs next session" is plausible. (Necessary vs sufficient condition analysis) |

   For each check: record `[PASS]` or `[FAIL] — <what is wrong and where in the file>`.

3. **Requirements coverage check** (only if requirements.md was found in step 1)
   - For each user story in requirements.md: verify the design addresses it — either in a decision, a flow diagram, or the file inventory; if not addressed, record `[FAIL] — requirement not addressed: "<story text>"`
   - For each item in the "In:" scope list: verify it appears somewhere in the design; if not, record `[FAIL] — in-scope item not addressed: "<item>"`
   - If requirements.md was not found: record `[NOTE] — requirements.md not found; coverage check skipped`

4. **Output report**
   - List all failures grouped at the top
   - List all passes below
   - Format each line as `[PASS]` or `[FAIL] — <what is wrong and where>`
   - If all checks pass: append `DESIGN OK` at the end

   Example output format (failures first):
   ```
   [FAIL] E2E workflow coverage — use case "export flow" has no sequence diagram; component diagram at line 12 does not satisfy this check
   [FAIL] No vague language — "could be" found at line 34

   [PASS] Flow or architecture diagram
   [PASS] Decisions have rationale
   [PASS] File/path inventory
   [PASS] No user stories
   [PASS] No convention-as-design
   [PASS] Requirements coverage — all 3 user stories addressed
   [PASS] Requirements coverage — all in-scope items addressed
   ```

   Or if all pass:
   ```
   [PASS] Flow or architecture diagram
   [PASS] E2E workflow coverage
   [PASS] Decisions have rationale
   [PASS] File/path inventory
   [PASS] No user stories
   [PASS] No vague language
   [PASS] No convention-as-design
   [PASS] Requirements coverage — all user stories addressed
   [PASS] Requirements coverage — all in-scope items addressed

   DESIGN OK
   ```

## Second-Run Behavior

The skill is deterministic and idempotent. Running twice on the same file with no changes produces identical output. Output is determined solely by the file contents, not by previous runs or external state.

## Error Handling

If input file does not exist: output `{input_file} not found — cannot run verification.` and stop. Do not proceed to checks.

If requirements.md is absent from the same folder: skip requirements coverage check, include `[NOTE] — requirements.md not found; coverage check skipped` in the report, and proceed with structural checks only.
