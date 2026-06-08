# Verify Requirements SOP

## Overview

Check a requirements.md file for structural correctness and completeness. Structural checks (1-9) verify the file has the right sections, formatting, and no implementation leakage. Completeness checks (10-15) verify data dependencies are explicit, scenarios are covered, language is precise, open questions are resolved, and user stories are testable.

Structural failures and most completeness failures are blocking. Scenario coverage (11) and boundary conditions (12) are advisory — they use `[CONSIDER]` instead of `[FAIL]`.

This is an atomic skill — no subagents, no web calls, no spawning. All checks are performed inline by the invoking agent.

## Parameters

- **Input file** (required): path to requirements.md supplied by the caller
  - Standalone invocation: user provides path as argument
  - Called by `/verify-spec`: file path passed by the orchestrator

## Steps

### Step 1 — Read file

Read the file at the provided path.

- If the file does not exist: output `{input_file} not found` and stop. Do not proceed to checks.

---

### Structural Checks (2-10)

### Step 2 — Goal statement

Locate a clear one-sentence goal near the top of the file (not buried in prose).

- Present: `[PASS] Goal statement`
- Absent: `[FAIL] Goal statement — not found near top of file`

### Step 3 — User stories present

Scan the file for at least one user story block.

- At least one exists: `[PASS] User stories present`
- None found: `[FAIL] User stories present — no user stories found`

### Step 4 — User stories format

For each user story found, verify both "I want" and "so that" clauses are present.

- All stories complete: `[PASS] User stories format`
- Any story missing a clause: `[FAIL] User stories format — story at line {N} missing "{clause}"`

### Step 5 — In/Out scope defined

Verify explicit "In:" and "Out:" lists (or "In scope" / "Out of scope" sections) are present.

- Both sections exist: `[PASS] In/Out scope defined`
- Either missing: `[FAIL] In/Out scope defined — missing {In/Out} section`

### Step 6 — Constraints listed

Verify a "Constraints" section exists with at least one item.

- Present with items: `[PASS] Constraints listed`
- Missing or empty: `[FAIL] Constraints listed — section missing or empty`

### Step 7 — No implementation details

Scan for tool names, code references, or internal mechanics (e.g. "we use the Write tool", "we check with Glob", specific function names, API endpoints).

Expected output format examples and acceptance criteria are acceptable — do not flag them.

- None found: `[PASS] No implementation details`
- Found: `[FAIL] No implementation details — found at line {N}: "{excerpt}"`

### Step 8 — No design decisions

Scan for architectural choices: internal file locations, tool selection, SOP structure format, "we chose X over Y", algorithm selection, data structure choices.

Expected output format and template examples are acceptable — do not flag them.

- None found: `[PASS] No design decisions`
- Found: `[FAIL] No design decisions — found at line {N}: "{excerpt}"`

### Step 9 — No ungrounded extrapolation

For each user story, check whether specifics (tool names, file names, skill designs, architectural concepts) are traceable to stated user input or are standard domain terms. Flag stories that contain specifics the user did not mention — these indicate agent extrapolation not validated as a requirement.

- All grounded: `[PASS] No ungrounded extrapolation`
- Ungrounded specifics found: `[FAIL] Ungrounded extrapolation — story at line {N} introduces "{specific}" not present in user input`

### Step 10 — No duplicate patterns

Scan all user stories for repeated interaction patterns described with different nouns. If two or more stories describe the same shape ("before doing X, do Y first" with different X/Y values), flag as a unification opportunity — they are one mechanism, not two separate features.

- No duplicates: `[PASS] No duplicate patterns`
- Found: `[FAIL] Duplicate pattern — stories at lines {N} and {M} describe the same interaction shape: "{pattern}"`

---

### Completeness Checks (11-16)

### Step 11 — Data dependency scan [blocking]

1. Collect all in-scope items.
2. For each item, extract concrete data artifact names — nouns that name a specific thing the system produces, consumes, or stores. Skip generic nouns: "user", "data", "input", "output", "system", "result", "response", "request", "file", "item".
3. Build a cross-reference: for each artifact name that appears in 2+ in-scope items, check whether the requirements state a dependency relationship between those items (words like "depends on", "requires output of", "uses X from", "after", "feeds into", or explicit ordering).
4. If in-scope items are single-line bullets with no elaboration and contain shared artifact names, flag the lack of elaboration itself.

- All shared artifacts have stated dependencies, OR no shared artifacts found: `[PASS] Data dependencies`
- Shared artifact with no stated dependency: `[FAIL] Data dependencies — "{artifact}" appears in items at lines {N} and {M} with no dependency stated`

### Step 12 — Scenario coverage [advisory]

For each in-scope item, check for state-implying keywords ("first time", "already exists", "previous", "cache", "history", "stored", "persisted", "remembered") or variable-cardinality input (nouns: "list", "collection", "batch", "set", "array", "multiple", "each", "all").

For items that match, check whether the spec addresses:
- (a) First-run / empty state
- (b) Repeat-run / prior output exists
- (c) Empty input
- (d) Boundary input (max/edge)

Items with no state keywords and no variable-cardinality keywords are exempt — skip them.

- All applicable scenarios addressed or item is exempt: `[PASS] Scenario coverage`
- Missing scenarios: `[CONSIDER] Scenario coverage — item at line {N} implies {state/variable input} but only describes the happy path. Missing: {list of a/b/c/d not addressed}`

### Step 13 — Boundary conditions [advisory]

For each requirement mentioning a countable or sized input (keywords: "list", "collection", "file", "batch", "set", "array", "items", "entries", "count", "N"), check whether zero, one, and max/overflow cases are addressed anywhere in the requirements.

- Boundary cases stated, explicitly deferred, or no countable inputs found: `[PASS] Boundary conditions`
- Missing: `[CONSIDER] Boundary conditions — line {N} mentions "{keyword}" but does not address empty or max cases`

### Step 14 — Requirements smell scan [blocking]

Scan **user stories and in-scope items only** (not constraints, not rationale sections) for:

1. **Vague qualifiers**: "appropriate", "sufficient", "reasonable", "properly", "as needed", "etc.", "and so on", "handle gracefully", "correctly", "suitably", "adequate"
2. **Missing error paths**: in-scope item describes a happy-path action with no corresponding error/failure mention anywhere in the requirements (search the full file for error handling of that item)
3. **Assumed ordering**: "then", "after", "next", "once X is done" used to imply sequencing without explicit ordering in scope or constraints
4. **Implicit universals**: "all", "every", "any", "always", "never" without stated bounds or exceptions

For each smell found, record the category, line number, and excerpt.

- Zero smells in user stories and in-scope items: `[PASS] Requirements smells`
- Smells found: `[FAIL] Requirements smells — {N} smells found:` followed by a list: `  - [{category}] line {N}: "{excerpt}"`

### Step 15 — Open question resolution [blocking]

Scan the entire file for markers: "TBD", "TODO", "?", "needs research", "to be determined", "open question", "assume", "unclear", "not yet decided", "pending".

For each marker found, check if it has:
- A resolution (decision recorded in the same section or nearby), OR
- A researched default (source cited), OR
- An explicit deferral with rationale ("deferred because...", "out of scope because...")

Question marks in section headers (e.g. "## What if X?") and rhetorical questions in rationale text are exempt — only flag markers that indicate unresolved decisions.

- All markers resolved, deferred with rationale, or no markers found: `[PASS] Open questions resolved`
- Unresolved markers: `[FAIL] Open questions resolved — {N} unresolved:` followed by a list: `  - line {N}: "{excerpt}"`

### Step 16 — User story testability [blocking]

For each user story, check that at least one acceptance criterion or testable condition is present. Look for:
- Keywords: "given", "when", "then", "verify", "accept", "criteria", "expected", "must", "should produce", "results in"
- A bullet list following the story that specifies observable outcomes
- An explicit acceptance criteria section linked to the story

- Every story has at least one testable condition: `[PASS] User story testability`
- Story without testable condition: `[FAIL] User story testability — story at line {N} has no acceptance criteria or testable condition`

### Step 17 — Irreversible-action scenario walkthrough [blocking]

For each in-scope item or user story that describes an irreversible action (delete, remove, graduate, overwrite, purge, drop), construct a scenario where all stated trigger criteria are satisfied but the original problem recurs. If the scenario is plausible, the criteria are necessary but not sufficient — flag as insufficient.

Test: for each irreversible action, ask "Can the trigger criteria all be true while the underlying problem persists?" If yes, the criteria need strengthening.

- All irreversible actions have sufficient criteria, OR no irreversible actions found: `[PASS] Irreversible-action criteria`
- Insufficient criteria found: `[FAIL] Irreversible-action criteria — item at line {N} triggers irreversible action "{action}" but criteria are necessary-only: "{scenario where criteria pass but problem persists}"`

---

### Report Compilation (Step 18)

### Step 18 — Compile report

Group all check results into four sections in this order:

**Group 1 — Structural failures:** all `[FAIL]` results from checks 2-10.

**Group 2 — Completeness failures:** all `[FAIL]` results from checks 11, 14, 15, 16, 17.

**Group 3 — Completeness advisories:** all `[CONSIDER]` results from checks 12, 13.

**Group 4 — Passes:** all `[PASS]` results from all checks.

Format:
```
[FAIL] {check name} — {evidence}
[FAIL] {check name} — {evidence}

[CONSIDER] {check name} — {evidence}

[PASS] {check name}
[PASS] {check name}

SUMMARY: {N} failures, {M} advisories, {P} passes
```

If zero failures (advisories are allowed): append `REQUIREMENTS OK` after the SUMMARY line.

Output the compiled report as inline text in the agent response. Do not write any files.

## Second-Run Behavior

Deterministic and idempotent. Running twice on the same file with no changes produces identical output. Output is determined solely by the file contents, not by previous runs or external state.

## Error Handling

If input file does not exist: output `{input_file} not found` and stop. Do not proceed to checks.
