# Verify Task SOP

## Overview

`/verify-task` validates a task.md file against structural requirements and checks that design.md components are covered by tasks. It is a leaf skill — called directly for single-file checks or internally by `/verify-spec` when verifying a full spec folder. It does not fix violations — it reports them.

## Parameters

- `{input_file}` — absolute path to the task.md file to verify (e.g., `/path/to/project/specs/foo/task.md`). Required.
- `design.md` — derived automatically: same folder as `{input_file}`, filename `design.md`. Optional — if absent or empty, design coverage check is skipped with a note.
- `requirements.md` — derived automatically: same folder as `{input_file}`, filename `requirements.md`. Optional — if absent or empty, requirements-verification task check is skipped with a note.

## I/O Contract

**Output on PASS:** Single line: `TASK OK`

**Output on FAIL:** One `[FAIL] — <violation description and location>` line per violation, followed by `TOTAL FAILURES: [count]`

**Output on fatal input error:** Single line: `[FAIL] — <reason>` (e.g., task.md not found, path is a directory)

## Second-Run Behavior

Running `/verify-task` twice on the same unmodified task.md produces identical output. A file that passed on first run continues to pass; a file that failed remains failed until violations are fixed. Output is deterministic — no randomness, no state tracking.

## Steps

1. Validate input path: read `{input_file}`. If not found, output `[FAIL] — task.md not found at {input_file}` and stop. If `{input_file}` is a directory path, output `[FAIL] — {input_file} is a directory, not a file` and stop.

2. Derive companion file paths from the directory of `{input_file}`:
   - `design_path` = same folder + `design.md`
   - `requirements_path` = same folder + `requirements.md`
   - Attempt to read each. If a file is absent or has no content, note it (do not fail) and skip its associated check in later steps.

3. Run structural checks on task.md:
   - **Checkbox format**: all task items must use `- [ ]` format. Reject prose todos and numbered lists without checkboxes. Flag as `[FAIL] — non-checkbox items found at [location]` if violated.
   - **Open questions section**: file must contain a section named exactly "Open questions" or "Questions" with at least one item beneath it. Flag as `[FAIL] — no open questions section` if absent or empty.
   - **Deferred items separation**: deferred items must appear in a distinct section with a name from: "Later", "Build later", or "Deferred". If deferred items appear in the main (non-deferred) task section, flag as `[FAIL] — deferred items mixed with immediate tasks`.
   - **No completed items**: no `- [x]` checked items may exist anywhere in the file. Flag as `[FAIL] — completed items found at [location]` if any are present.
   - **Concrete action verbs**: all tasks must begin with a concrete action verb. Reject any task whose verb is from the vague-verb class: think, explore, consider, discuss, look into, investigate (unless paired with a concrete output artifact), understand. Flag as `[FAIL] — non-concrete tasks at [location]` for each violation.

4. If `requirements_path` file was successfully loaded and is non-empty: verify the last item in the first non-deferred tasks section (the "Immediate" section — the first top-level tasks section in the file that is not a deferred/later section) is a requirements-verification task (e.g., "Verify all requirements from requirements.md are satisfied"). Flag as `[FAIL] — no requirements verification task at end of Immediate section` if missing.

5. If `design_path` file was successfully loaded and is non-empty:
   - For each file in the design's file inventory marked "Create" or "Edit": search task.md for a task that references the file name or a clear slug/camelCase equivalent of it. Flag as `[FAIL] — design component not tasked: "[file name]"` for each unmatched file.
   - For each major component or flow step named in the design diagram or described as a discrete component: search task.md for a task that references the component name or an equivalent label. Flag as `[FAIL] — design flow component not tasked: "[component name]"` for each unmatched component.

6. Aggregate all failures. If zero failures: output `TASK OK`. If one or more: output each failure as a separate line in the format `[FAIL] — <description and location>`, then end with `TOTAL FAILURES: [count]`.

## Failure Handling

- **task.md not found**: output `[FAIL] — task.md not found at {input_file}` and stop. No further checks.
- **{input_file} is a directory**: output `[FAIL] — {input_file} is a directory, not a file` and stop.
- **design.md absent or empty**: skip design coverage check. Note in output if PASS: `TASK OK (design.md not found — coverage check skipped)`.
- **requirements.md absent or empty**: skip requirements-verification task check. No output change for PASS.
- **Malformed design.md** (no file inventory or diagram parseable): skip design coverage check. Note: `[FAIL] — design.md found but file inventory and diagram components could not be parsed; coverage check skipped`.
