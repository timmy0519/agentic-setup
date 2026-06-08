---
name: verify-requirements
description: "[atomic] Verify a requirements.md file for structural correctness AND completeness. Structural checks (goal, user stories, scope, constraints, no implementation leakage) are blocking. Completeness checks (data dependencies, scenario coverage, boundary conditions, smells, open questions, testability) catch gaps before design begins — failures block, advisories suggest. Fast, no web calls. Called by /verify-spec or standalone."
---

## I/O Contract

**Inputs:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | path | yes | Path to the `requirements.md` file to verify |

**Output:**

- Inline text report in the agent response (not a file write)
- Format: results grouped by severity — structural failures first, completeness failures second, completeness advisories third (`[CONSIDER]`), all passes last
- SUMMARY line with failure count, advisory count, pass count
- `"REQUIREMENTS OK"` appended only when zero failures (advisories do not block)

**Output schema types:**
- `check_result`: enum — `[PASS]` | `[FAIL]` | `[CONSIDER]`
- `verdict`: enum — `"REQUIREMENTS OK"` (zero failures) | summary with failure/advisory counts (any fail)

**Second-run behavior:** Deterministic — same file, same output, no state between runs.

## Trigger Phrases

- "verify these requirements"
- "check requirements.md"
- "run verify-requirements on ..."
- "check the requirements file"
- "verify requirements for ..."
- called internally by `/verify-spec` and `/spec-authoring` with a file path argument

## What It Does

Runs 15 checks in two groups:

**Structural checks (1-9) — blocking:**
1. Goal statement present
2. User stories present
3. User stories format ("I want" + "so that" clauses)
4. In/Out scope defined
5. Constraints listed
6. No implementation details
7. No design decisions
8. No ungrounded extrapolation
9. No duplicate patterns

**Completeness checks (10-15):**
10. Data dependency scan (blocking)
11. Scenario coverage (advisory)
12. Boundary conditions (advisory)
13. Requirements smell scan (blocking)
14. Open question resolution (blocking)
15. User story testability (blocking)

Compiles a grouped report: failures first, advisories second, passes last. Adds SUMMARY line and `REQUIREMENTS OK` verdict when zero failures.

## What It Does NOT Do

- Does not check design.md, task.md, or any other file
- Does not access the web or call external tools
- Does not create or modify any files
- Does not spawn subagents
- Does not evaluate whether requirements are *correct* — checks structural format and completeness coverage

## Routing Boundaries

| If the user wants... | Use instead |
|---------------------|-------------|
| Verify all spec files (requirements + design + task) | `/verify-spec` |
| Verify design.md | `/verify-design` |
| Verify task.md | `/verify-task` |
| Check a research note format | `/verify-format` |
| Write requirements from scratch | `/spec-authoring` |

## Invocation

Run the verification workflow defined in `references/sop.md`.
