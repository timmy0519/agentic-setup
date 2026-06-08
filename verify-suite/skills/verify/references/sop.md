## Verify — Orchestrator SOP

This SOP defines the mechanical pipeline for the unified verify orchestrator. The AI orchestrator calls scripts for deterministic work and focuses exclusively on: argument parsing, subagent dispatch, tolerant NL parsing, and report structuring.

**Scripts directory:** `${CLAUDE_PLUGIN_ROOT}/skills/verify/scripts/`
**Rules directory:** `${CLAUDE_PLUGIN_ROOT}/skills/verify/rules/`
**Artifact config:** `${CLAUDE_PLUGIN_ROOT}/skills/verify/artifact-config.yaml`

---

### Step 0: Rule health staleness check

Run at the start of every invocation:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/verify/scripts/describe.py --health-check
```

If the script outputs `STALE` (last_review_date > 90 days or file missing), prepend this line to the final report:

```
[CONSIDER] Rule health review overdue — last review: {date}
```

Continue with the pipeline regardless.

---

### Step 1: Parse caller arguments

Extract from the invocation:

| Argument | Required | Notes |
|----------|----------|-------|
| `artifact_path` | yes | Path to the spec file being verified |
| `--type` | no | Comma-separated artifact type(s). If absent, infer from filename |
| `--skip-phase` | no | `structural` — requires `--reason` |
| `--skip-rules` | no | Comma-separated rule IDs — requires `--reason` |
| `--reason` | conditional | Required with `--skip-phase` or `--skip-rules` |
| `--rules` | no | Comma-separated rule IDs — à la carte selection, skips config lookup |
| `--no-adversarial` | no | Skip the Mode-2 adversarial pass (Step 9.5) — requires `--reason` |
| `--adversarial` | no | Force the Mode-2 adversarial pass even on a small/intermediate artifact |
| `--list-types` | no | Describe mode — list types and exit |
| `--describe <type>` | no | Describe mode — show rules for type and exit |

**If `--rules` is provided:** jump to Step 2b (à la carte mode).
**If `--list-types` is set:** jump to Step 1a.
**If `--describe <type>` is set:** jump to Step 1b.

---

### Step 1a: List types mode

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/verify/scripts/describe.py
```

Output the result and **stop** — no rule dispatch.

---

### Step 1b: Describe type mode

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/verify/scripts/describe.py <type>
```

Output the result and **stop** — no rule dispatch. If the script returns a "type not found" error, output it with the list of available types.

---

### Step 2: Resolve artifact type and rule list

**Type resolution fallback chain:**
1. If `--type` is provided, use it (supports comma-separated: `--type requirements,design`)
2. Else infer from filename: `requirements.md` → `requirements`, `design.md` → `design`, `task.md` → `task`
3. If neither matches, output error: `Error: Cannot infer artifact type from filename '{name}'. Use --type to specify.` and **stop**.

Derive the spec folder from the artifact path (parent directory of the artifact file).

**Call resolve.py:**

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/verify/scripts/resolve.py <type> --spec-folder <spec_folder>
```

For multi-type: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/verify/scripts/resolve.py <type1,type2> --spec-folder <spec_folder>`

The script returns JSON: `[{id, path, model_hint, stage, severity, inputs}]`

**If the script returns an error** (missing config, malformed YAML), output the error and **stop**.

**Apply --skip-rules:** remove any rules whose `id` matches the skip list. Record each as:
```
[SKIP] {rule-name} — reason: "{reason}"
```

---

### Step 2b: À la carte mode (--rules)

When `--rules rule1,rule2,rule3` is provided, skip artifact-config.yaml lookup entirely:

1. Split the comma-separated rule IDs.
2. For each rule ID, resolve the path using the same resolution order: `rules/structural/{id}.md` → `rules/general/{id}.md`. If neither exists, record `[FAIL] {id} — rule file not found`.
3. Extract frontmatter from each found rule file to get `model_hint`, `severity`, `inputs`.
4. **All specified rules run as quality phase** — no structural gate applies.
5. Skip Step 3 (consistency check) and Step 5–6 (structural phase/gate). Jump directly to Step 7 (quality phase) with the resolved rule list.

**When to use:** intermediate outputs, ad-hoc checks, or compiler-worker verification of a single rule. When `--rules` is provided, no structural gate applies — all specified rules run as quality phase.

---

### Step 3: Config-rules consistency check

Before dispatch, verify config-rules consistency:

1. **Dangling references:** for each rule in the resolved list, confirm the `path` file exists. If missing, record `[FAIL] {rule-id} — rule file not found` and remove from dispatch list.
2. **Orphaned files:** list all `.md` files in `rules/general/` and `rules/overlays/` that are not in the resolved list. If any, note for the report header: `[CONSIDER] Orphaned rule files: {list}`

---

### Step 4: Check cache

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/verify/scripts/cache.py check <artifact_path>
```

Returns JSON: `{hit: bool, structural: verdict, quality: verdict}`

**If cache hit** (hash matches and both phases have verdicts):
- Format a cached report with `[SKIP] All rules — cached verdict` per phase
- Include the cached verdicts in the summary
- Output report and **stop**

**If cache miss:** continue to Step 5.

---

### Step 5: Structural phase

**If `--skip-phase structural` is set:**
- Record: `[SKIP] Structural phase skipped — reason: "{reason}"`
- Jump to Step 7 (quality phase)

**Otherwise:** dispatch all rules where `stage == "structural"`.

**Agent dispatch — parallel, one subagent per rule:**

For each structural rule, spawn an Agent subagent with the following prompt. The subagent reads all files itself — the orchestrator only passes paths.

```
You are evaluating a spec artifact against a single rule.

Read these files in order:

1. Verdict guide: ${CLAUDE_PLUGIN_ROOT}/skills/verify/references/verdict-guide.md
   — defines verdicts, calibration, and how to report your finding
2. Rule: {rule.path}
   — your evaluation prompt is the markdown body after the frontmatter
   {if rule.overlay_path: 3. Domain overlay: {rule.overlay_path}
   — read and apply as additional evaluation context}
4. Artifact: {artifact_path}
   — this is the file you are evaluating
{for each additional input in rule.inputs (other than "artifact"):}
5. {input_name}: {spec_folder}/{input_name}.md
   — if file missing, report SKIP with "missing input: {input_name}.md"

Evaluate the artifact against the rule, then report your finding using the method described in the verdict guide. Your rule's severity is in its frontmatter.
```

Set the Agent `model` parameter from the rule's `model_hint` field (`haiku`, `sonnet`, or `opus`).

Dispatch all structural rules in parallel (multiple Agent calls in one response). Wait for all to complete.

---

### Step 6: Structural gate check

Collect all structural subagent responses. For each response, extract the finding using this priority:

**Layer 1 — Script output (best):** If the subagent invoked `report.py`, its output is already structured JSON with `rule_id`, `verdict`, `severity`, `evidence`, `confidence`. Use directly.

**Layer 2 — Labeled template:** If the response contains `VERDICT:`, `RULE:`, `EVIDENCE:` labels, extract the labeled fields. Pipe through `report.py --parse` if needed:
```bash
echo "<subagent_response>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/verify/scripts/report.py --parse
```

**Layer 3 — NL fallback:** If neither script output nor labels are present, scan for verdict keywords (PASS, FAIL, CONSIDER) — use the last occurrence. Pipe through `report.py --parse` to normalize.

**After extracting the verdict:**
- Map severity: if the rule has `severity: advisory` and the subagent says FAIL, record as CONSIDER instead
- If no verdict can be extracted at all, record as `[FAIL] {rule-id} — evaluation error: no verdict returned`

**Call gate.py** with the structural results:

```bash
echo '<json_array_of_verdicts>' | python3 ${CLAUDE_PLUGIN_ROOT}/skills/verify/scripts/gate.py
```

Returns: `{pass: bool, fail_count: int}`

**If gate fails** (any FAIL in structural results):
- Record quality phase as: `[SKIP] Quality phase skipped — structural failures must be resolved first`
- Jump to Step 9 (report)

**If gate passes:** continue to Step 7.

---

### Step 7: Quality phase

Dispatch all rules where `stage == "quality"` using the same Agent dispatch pattern as Step 5.

Quality rules typically use `model_hint: sonnet` or `model_hint: opus` (for cross-artifact rules).

For cross-artifact rules (`inputs` includes names other than `artifact`):
- Resolve each input: `{spec_folder}/{input_name}.md`
- If an input file is missing, record the rule as `[SKIP] {rule-name} — missing input: {input_name}.md` and do not dispatch

Dispatch all applicable quality rules in parallel. Wait for all to complete.

---

### Step 8: Parse quality findings

Tolerantly parse each quality subagent response using the same approach as Step 6:

- Extract verdict keyword (PASS, FAIL, CONSIDER)
- Extract evidence (the text around the verdict)
- Apply severity mapping: `severity: advisory` + violation → CONSIDER
- No parseable verdict → `[FAIL] {rule-id} — evaluation error: no verdict returned`

---

### Step 9: Update cache

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/verify/scripts/cache.py update <artifact_path> structural <structural_verdict>
python3 ${CLAUDE_PLUGIN_ROOT}/skills/verify/scripts/cache.py update <artifact_path> quality <quality_verdict>
```

Where `<verdict>` is PASS if zero FAILs in that phase, FAIL otherwise.

---

### Step 9.5: Adversarial pass (Mode 2) — default-on for substantial/final artifacts

**Why this step exists (run it by default — do not skip reflexively):** Steps 5–8 are Mode 1 — *conformance*. They ask "does the artifact have property X?" against a fixed rule pack. They cannot catch a failure mode nobody has codified yet: an unimplementable claim, a race, a regression, silent data loss, over-engineering, an edge case never generated. Writer-self-verify makes this worse — the writer's blind spots are exactly what the rules don't encode. Empirically, an artifact can pass Mode 1 with **zero failures** and still carry HIGH-severity defects: on `specs/ac-oriented-workflow-tracking/design.md` the checklist passed clean while the adversarial pass found a HIGH migration-crash bug and a regression introduced in the same session. **Shipping a substantial or final artifact on Mode 1 alone ships those blind.** That is why Mode 2 is the default tail of the pipeline, not an opt-in extra.

**Run UNLESS any of:**
- `--no-adversarial` is set (record `[SKIP] Adversarial pass — reason: "{reason}"`; `--reason` required).
- The structural gate failed (Step 6) — fix conformance first; an adversarial pass on a malformed artifact is noise.
- The artifact is **trivial / intermediate**: a tiny or low-stakes file, or a mid-pipeline leaf verify that is not the final artifact (e.g. verifying `requirements.md` while `design.md`/`task.md` are still to come). For these, skip silently unless `--adversarial` forces it. Rule of thumb: run on the *final* artifact of a pipeline and on any standalone verify of a substantial design/spec/code artifact; skip on throwaway/intermediate checks.

**How:** dispatch the adversarial reviewer — the `adversarial-reviewer` agent for a single grounded pass, or the `/adversarial-review` skill for a full parallel multi-lens pass on high-stakes artifacts. Pass: the artifact, its stated intent, and grounding (sibling `requirements.md`/`design.md`/`.decisions.md` + the resolved rule files as principles). It returns severity-rated, source-grounded findings + reliability ratings.

**One pass is a sample, not an audit.** Independent passes find largely different real defects (high precision, partial non-overlapping recall). For a substantial standalone verify, one pass is the right default. For a **high-stakes/final** artifact, run **2–3 independent passes and UNION** the deduped findings (the skill, or the agent repeated with fresh context) — the recall gain is from independent samples. Judge findings against the artifact's DESIGN claims and its own scope section, not the unmodified source: down-rate "not implemented yet" and scope-deferred items; a single pass over-/under-reports either way.

**Gate semantics — advisory, NOT blocking (soft-gate):** the adversarial findings do NOT flip the Mode 1 PASS/FAIL verdict. They are appended to the report for the lead/user to act on. A decision to ship past a HIGH-severity adversarial finding is the lead's to make and should be recorded with a reason. (Recurring adversarial findings graduate into Mode 1 checklist rules via `/flag-imp` — the cheap conformance pass absorbs them over time.)

---

### Step 10: Format and output report

Assemble the report in this format:

```
## Verify Report: {artifact_type}

{if orphaned files found:}
[CONSIDER] Orphaned rule files: {list}

{if rule health stale:}
[CONSIDER] Rule health review overdue — last review: {date}

### Structural
{for each structural rule, ordered: FAIL first, then CONSIDER, SKIP, PASS}
[{VERDICT}] {Rule name} — {evidence or reason}

### Quality
{for each quality rule, same ordering}
[{VERDICT}] {Rule name} — {evidence or reason}

{if Step 9.5 ran:}
### Adversarial (Mode 2) — advisory, does not gate Mode 1 verdict
{confirmed findings, severity-ordered: HIGH first}
[{HIGH|MEDIUM|LOW}] {finding} — span: "{quote}" ({location}); violates: {requirement}; scenario: {concrete}
{then reliability ratings + most-dangerous-gap}
{if Step 9.5 skipped:}
[SKIP] Adversarial (Mode 2) — {reason: trivial/intermediate | --no-adversarial reason | structural gate failed}

SUMMARY: {N} failures, {M} advisories, {P} passes, {S} skipped{if adversarial ran: ; adversarial: {H} high, {Md} medium, {L} low (advisory)}
{if zero Mode-1 failures: ARTIFACT_TYPE OK}{if adversarial HIGH findings: — NOTE: {H} HIGH adversarial finding(s) — advisory, lead decision required}
```

Where `ARTIFACT_TYPE OK` is one of: `REQUIREMENTS OK`, `DESIGN OK`, `TASK OK`.

If multiple types were run (multi-type mode), output one section per type, then a combined summary.

---

### Error handling summary

| Error | Action |
|-------|--------|
| Artifact file not found | Output error, stop |
| Unknown artifact type (no --type, filename doesn't match) | Output error, stop |
| Config missing or malformed | Output error from resolve.py, stop |
| Rule file missing | Record `[FAIL] {id} — rule file not found`, continue |
| Rule frontmatter unparseable | Record `[FAIL] {id} — rule load error`, continue |
| Subagent returns no parseable verdict | Record `[FAIL] {id} — evaluation error: no verdict returned` |
| Subagent timeout/crash | Record `[FAIL] {id} — evaluation error: subagent failed` |
| Cross-artifact input file missing | Record `[SKIP] {id} — missing input: {name}.md` |
| Cache file missing/corrupted | Treat as cache miss, run all phases |
| Rule health file missing | Report `[CONSIDER]` staleness warning, continue |
