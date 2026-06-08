## Verify Content — Depth Review SOP

## Overview

**Skill type**: Orchestrator

**Purpose**: Review each section of a research note for depth and completeness — not factual accuracy. Automatically expand thin sections using sonar-pro. Iterate until the note meets the sufficiency threshold. Perplexity is trusted as the source of truth; do not re-verify Perplexity-sourced content.

**Pipeline shape**: 6-stage sequential with branching on flag types
1. input-loader (inline)
2. requirements-coverage-checker (agent dispatch — skipped if no requirements.md)
3. requirements-coverage-validator (agent dispatch — skipped if Stage 2 skipped)
4. section-depth-evaluator (agent dispatch, one per section)
5. section-expander (agent dispatch, per-flag retry loop — user gate before this stage)
6. source-validator (agent dispatch) + Stage 6 report (inline)

**Negative triggers**:
- Do NOT invoke on bare "verify my note" — route to `/verify-note` which runs both format and content checks
- Do NOT invoke for format-only checks — route to `/verify-format`
- Do NOT invoke for spec verification — route to `/verify-spec`

---

## Parameters

| Name | Source | Type | Default | Valid values | Required |
|------|--------|------|---------|--------------|----------|
| `note_path` | user message or argument | file path string | — | any `.md` under `Research/` | yes |
| `requirements.md` | read from disk, same folder as `note_path` | file (implicit) | empty — skip requirements coverage stages | `.md` file with "Must answer" and/or "Expected action items" headings | no |

---

## Depth criteria (apply per section)

Rate each section SUFFICIENT or flag it. A section is SUFFICIENT if a reader unfamiliar with the topic can:
- Understand the core idea without googling
- Know how it compares to things they already know
- Understand the key tradeoffs without reading further

| Flag | Principle | Condition |
|------|-----------|-----------|
| `NEEDS EXPANSION` | **Self-containment** — a reading unit must be independently comprehensible without external lookup | Section violates self-containment: raises a question a curious reader would naturally ask but does not answer it; OR comparison feels one-dimensional (just names, no angles); OR a key concept is mentioned but not explained. *Test*: would a reader need to google to understand this section? |
| `NEEDS GAP DEPTH` | **Impact assessment** — a gap claim must characterize impact dimensions sufficient to drive action | Gap analysis section claims something is missing but omits any of the three impact dimensions: (1) workaround effort, (2) gap type (surface/UX vs. architectural), (3) closure trajectory. *Test*: could a decision-maker act on this gap description without asking follow-up questions? |
| `NEEDS COMPARISON` | **Attribution accuracy** — credit for a capability must go to the entity that actually produces it (product vs. model vs. ecosystem) | Section claims a strength or differentiator without completing the feature uniqueness check. *Test*: is the credited entity actually the source of the capability, or would the same behavior exist with the same model in a different tool? |
| `NEEDS DIAGRAM` | **Visual structure** — mechanisms, flows, and relationships must be represented in the highest-fidelity format that fits the content | A mechanism or flow is explained in prose only; a sequence or component diagram would make it materially clearer |
| `NEEDS SOURCE VALIDATION` | **Claim-source proportionality** — the strength of a claim must be proportional to the strength of its source | A claim uses superlatives ("unique," "only," "exclusive," "always," "best," or similar) and is backed only by a news article or comparison blog — not official docs or forum discussion. *Test*: does the source type match the claim strength? |
| `NEEDS CX SECTION` | **User-centered IA** — information architecture must lead with user experience, not feature inventory | First substantive section is a feature list, comparison table, or architecture diagram with no prior user experience section (applies to AI-product notes only). *Test*: does organizational logic reflect user goals or product taxonomy? |
| `NEEDS GROUNDING` | **Mechanistic grounding** — non-obvious claims must be supported by a mechanism explanation or link to one | A non-obvious comparative or performance claim exists with no mechanism sentence and no `[[#Section]]` link to a section that explains it |
| `NEEDS DISAMBIGUATION` | **Confusion anticipation** — claims that invite predictable wrong assumptions must preemptively address them | A key claim would cause a reader familiar with adjacent concepts to make a predictable wrong assumption — and the note does not preemptively address it |
| `NEEDS REQUIREMENTS COVERAGE` | **Requirements traceability** — every "Must answer" question must have a clear answer in the note | A "Must answer" question from requirements.md is not clearly answered in the note |
| `NEEDS ACTION ITEM` | **Deliverable completeness** — every expected action item must have a corresponding entry in task.md | An "Expected action item" from requirements.md has no corresponding entry in task.md |

---

## Feature uniqueness check (attribution accuracy)

Run this check on every claimed strength or differentiator before rating a section SUFFICIENT. **Principle**: attribution accuracy — credit for a capability must go to the entity that actually produces it (product design, underlying model, or ecosystem).

1. Determine whether the two or three most popular comparable products also have this feature.
   - If yes: do not treat the feature as a differentiator. Identify the design difference that produces a different user experience.
   - If no: note it as genuinely distinctive; verify with user community feedback that users actually notice it.

2. Identify what users say about each product's implementation of this feature.
   - Use community discussion to drive the verdict, not feature checklists.
   - If no CX difference is found in community discussion, treat the feature as table-stakes and remove the differentiator claim.

3. Determine whether the praised behavior is specific to this product's design or would be identical with the same underlying model in a different tool.
   - If the behavior would be identical with the same model elsewhere: it is a model advantage, not a product advantage. Relabel accordingly.

If a section claims advantage without completing these three checks, flag it as `NEEDS COMPARISON`.

---

## Diagram check

After reviewing or expanding any section, apply this check:

- If the section explains a flow, decision, or interaction over time and has no sequence diagram: flag as `NEEDS DIAGRAM`.
- If the section explains what parts exist and how they relate and has no component diagram: flag as `NEEDS DIAGRAM`.
- This check applies to any sub-section added during expansion, not only to top-level sections.

---

## Analogy and intuition rule

Every analogy must be paired with the key intuition — the actual mechanism or architectural reason that enables the difference.

- If an explanation states what is different but not why: flag as `NEEDS EXPANSION`.
- Vague contrasts ("X is deterministic, Y is flexible") without a mechanism explanation are insufficient.
- A complete explanation = analogy + "the reason this is possible is..."

---

## Subagent Contracts

Consolidated reference for all dispatched subagents. Each stage below references the applicable contract entry.

### requirements-coverage-checker

- **Receives**: `note_path` (absolute), `requirements.md` path (absolute), `requirements_data` (structured — "Must answer" questions + "Expected action items")
- **Produces**: list of `{ requirement_id, requirement_text, verdict: COVERED | UNCOVERED, evidence: quote from note }` for Must answer questions; list of `{ action_item, status: present | absent }` for Expected action items
- **Invoked at**: Stage 2

### requirements-coverage-validator

- **Receives**: `note_path` (absolute), `requirements.md` path (absolute), checker output (list of coverage verdicts from requirements-coverage-checker)
- **Produces**: validated coverage list — each COVERED verdict independently confirmed or downgraded to UNCOVERED with reason; final list used for Stage 4 branching
- **Invoked at**: Stage 3
- **Rationale**: requirements-coverage-checker self-grades its own COVERED verdicts; this separate validator closes the self-grading gap by independently verifying each COVERED verdict without relying on the checker's reasoning

### section-depth-evaluator

- **Receives**: `section_heading` (string), `section_body` (string), `note_context` (AI product or general — for CX section check); the 6 depth check criteria listed in Stage 4
- **Produces**: `{ section_name, flags: list of flag types triggered, pass: true | false }`
- **Invoked at**: Stage 4, once per major section; also re-invoked after section-expander writes to verify flag is cleared

### section-expander

- **Receives**: `section_text` (string), `flag_type` (string), `note_path` (absolute), targeted `perplexity_ask` query string built by orchestrator for the specific flag type and gap; sonar-pro instruction
- **Produces**: expanded section text written to note in-place; returns confirmation of write
- **Invoked at**: Stage 5, once per flag per section; retry cap applied per flag type (see Repair loops)

### source-validator

- **Receives**: `note_path` (absolute), list of `{ claim_text, query }` pairs — claim text extracted by orchestrator, targeted `perplexity_ask` query requesting forum discussion or official docs
- **Produces**: `{ claim, source, verdict: VALID | UNVERIFIABLE | CONTRADICTED }` per claim
- **Invoked at**: Stage 6 (consolidated after Stage 5)

---

## Repair loops

### Per-flag retry caps

| Flag type | Max expansion attempts | If still flagged after cap |
|-----------|----------------------|---------------------------|
| `NEEDS EXPANSION` | 2 | Mark section as TODO in note; add to task.md |
| `NEEDS GAP DEPTH` | 1 | Mark section as TODO in note; add to task.md |
| `NEEDS COMPARISON` | 1 | Mark section as TODO in note; add to task.md |
| `NEEDS SOURCE VALIDATION` | 1 | Add "(unverified, direction only)" inline; add claim to task.md |
| `NEEDS REQUIREMENTS COVERAGE` | 1 | Add to task.md as open question with "(requirement unmet)" marker |
| `NEEDS CX SECTION` | 1 (conditional — only if insufficient material in note) | Mark as TODO in note; add to task.md |
| `NEEDS DIAGRAM` | 0 (inline — orchestrator generates Mermaid directly) | If generation fails: add to task.md |
| `NEEDS DISAMBIGUATION` | 0 (inline — orchestrator writes clarification) | If domain knowledge insufficient: add to task.md |
| `NEEDS GROUNDING` | 0 inline; routes to NEEDS EXPANSION if no section found | If no section and expansion fails: add to task.md |
| `NEEDS ACTION ITEM` | 0 inline (write to task.md directly) | N/A |

### Global session cap

Maximum 6 section-expander dispatch calls per run. When the cap is reached, all remaining flagged sections are logged to task.md and the run proceeds to Stage 6 without further expansion.

### Empty response handling

If section-expander returns empty: retry once. If still empty after retry: mark section as TODO in note and continue with remaining sections.

### Post-expansion re-evaluation

After section-expander writes to a section: re-invoke section-depth-evaluator on that section. If the flag is cleared, mark the section as resolved. If the flag remains, apply the retry cap — decrement the remaining attempt count; if the cap is exhausted, mark as TODO.

---

## Failure handling

| Scenario | Trigger | Action | Escalation |
|----------|---------|--------|------------|
| `note_path` not found | File does not exist at load time | Abort; tell user: "Note not found at `{note_path}` — cannot proceed." Do not create or modify any files. | — |
| `requirements.md` not found | Path computed but file missing | Skip requirements coverage stages (2 + 3); note in Stage 6 report: "requirements.md absent — requirements coverage check skipped." | — |
| `requirements.md` present but unstructured | No "Must answer" or "Expected action items" headings found | Skip requirements coverage stages (2 + 3); note in Stage 6 report: "requirements.md present but unstructured — requirements coverage check skipped." | — |
| requirements-coverage-checker returns empty | Stage 2 empty output | Retry once. | Still empty → skip coverage stages; note in report: "coverage checker returned no output — requirements coverage check skipped." |
| requirements-coverage-validator returns empty | Stage 3 empty output | Retry once. | Still empty → use raw checker output with warning in report: "coverage verdicts unvalidated — validator returned no output." |
| section-expander write failure | Stage 5 file write error | Log section as TODO in task.md; continue with remaining sections. | — |
| section-expander returns empty | Stage 5 empty response | Retry once. | Still empty → mark section as TODO in note; continue. |
| User aborts at gate | Abort at Stage 5 user gate | Exit; return depth report (Stage 4 results) only. No note mutations. | — |
| Unrecognized flag type | section-depth-evaluator returns a flag not in the taxonomy | Log as TODO in task.md; skip expansion for that flag; continue. | — |
| Global expansion cap reached | 6 section-expander calls exhausted | Log all remaining flagged sections to task.md; proceed to Stage 6 report. | — |

---

## Second-run behavior

- Re-read the note from disk at `note_path`.
- Re-run all depth checks from scratch.
- Sections that currently pass the SUFFICIENT threshold are skipped — do not re-expand sections that already pass, regardless of prior run history.
- Sections that were deferred to task.md on a prior run: re-evaluate against current note content. If the note has since been updated to address the gap, mark as resolved. If still unaddressed, leave in task.md.
- If `requirements.md` was updated since last run: re-run requirements coverage stages (2 + 3) with updated requirements.
- Stage 6 report lists only items that changed on this run.

---

## Stage 1 — Load inputs

**Goal**: Resolve `note_path`, load `requirements.md` if present, verify `note_path` exists before proceeding.

**Dispatch**: inline (no subagent spawn)

1. Verify `note_path` exists. If the file does not exist: surface "Note not found at `{note_path}` — cannot proceed." Stop.
2. Read note text from `note_path`.
3. Check whether `requirements.md` exists in the same folder as `note_path`.
   - If present and structured: read it; extract "Must answer" questions and "Expected action items"; store as `requirements_data`.
   - If present but structurally unrecognizable (no "Must answer" or "Expected action items" headings): set `requirements_data` = empty; set `requirements_skip_reason` = "requirements.md present but unstructured."
   - If absent: set `requirements_data` = empty; set `requirements_skip_reason` = "requirements.md absent."
4. Produce `note_text`, `requirements_data`, `requirements_skip_reason`.

**Produces**: `note_text` (string), `requirements_data` (structured object or empty), `requirements_skip_reason` (string or null)

---

## Stage 2 — Requirements coverage check

**Goal**: Verify all "Must answer" questions and "Expected action items" from `requirements.md` are addressed in the note.

**Dispatch**: agent dispatch — requirements-coverage-checker

**Skip this stage if `requirements_data` is empty.** Proceed to Stage 4.

Dispatch **requirements-coverage-checker** (see Subagent Contracts) with:
- `note_path` (absolute)
- `requirements.md` path (absolute)
- `requirements_data`

On empty output: retry once. If still empty: skip; note in Stage 6 report (see Failure handling).

**Produces**: coverage verdict list passed to Stage 3.

---

## Stage 3 — Validate requirements coverage

**Goal**: Independently verify each COVERED verdict from Stage 2 to close the self-grading gap.

**Dispatch**: agent dispatch — requirements-coverage-validator

**Skip this stage if Stage 2 was skipped.**

Dispatch **requirements-coverage-validator** (see Subagent Contracts) with:
- `note_path` (absolute)
- `requirements.md` path (absolute)
- Coverage verdict list from Stage 2

On empty output: retry once. If still empty: use raw Stage 2 output with warning in Stage 6 report: "coverage verdicts unvalidated."

**Produces**: validated coverage verdict list. UNCOVERED items (including any COVERED verdicts downgraded by the validator) are flagged as `NEEDS REQUIREMENTS COVERAGE` or `NEEDS ACTION ITEM` and queued for Stage 5.

---

## Stage 4 — Rate each section

**Goal**: Assign a flag or SUFFICIENT to every major section by running all 6 depth checks grouped per section.

**Dispatch**: agent dispatch — section-depth-evaluator (one dispatch per major section)

For each major section in the note, dispatch **section-depth-evaluator** (see Subagent Contracts) with:
- `section_heading` (string)
- `section_body` (string)
- `note_context` (AI product or general)
- The 6 depth check criteria (each named by the principle it enforces):
  1. Attribution accuracy check — run on every claimed strength or differentiator (feature uniqueness check)
  2. Visual structure check — run after evaluating the section (diagram check)
  3. Claim-source proportionality check — scan for superlatives backed only by blog/news sources
  4. Mechanistic grounding check — confirm mechanism sentence or `[[#Section]]` link for non-obvious claims
  5. Confusion anticipation check — identify predictable wrong assumptions; check if note addresses them
  6. User-centered IA check (AI-product notes only) — confirm a user experience section appears before first feature/architecture section

**Produces**: `{ section_name, flags: list of flag types triggered, pass: true | false }` per section.

Collect all section results. Separate `NEEDS SOURCE VALIDATION` flags into a source-validation queue for Stage 6. All other flags proceed to Stage 5.

---

## Stage 5 — User gate + expand flagged sections

### User gate (before any note mutation)

Before dispatching section-expander, present the following to the user and wait for approval:

1. **What exists today**: section-depth-evaluator results — list of sections with their flags from Stage 4 (and Stage 3 UNCOVERED items)
2. **Before → After**: section-expander will expand flagged sections and write the expanded content to the note file in-place at `note_path`
3. **Why**: expansion permanently mutates the note content; user must approve before any write occurs
4. **Recommended default**: approve if the flagged gaps are legitimate; skip if the note is already sufficient for the use case
5. **Redirect options**:
   - Skip expansion: exit with the depth report from Stage 4 only; no note mutation
   - Abort: stop all processing; return Stage 4 results inline

If user aborts: exit; return depth report only; no note mutations.

If user approves: proceed to expansion below.

### Expansion

**Dispatch**: agent dispatch — section-expander (one dispatch per flag per section)

For each flagged section (excluding `NEEDS SOURCE VALIDATION` — handled in Stage 6):

Apply the repair for the flag type:

**NEEDS EXPANSION**

Dispatch **section-expander** with:
- `section_text`, `flag_type` = `NEEDS EXPANSION`, `note_path` (absolute)
- Targeted `perplexity_ask` query focused on the specific gap (not the full topic); sonar-pro instruction

After write: re-invoke section-depth-evaluator on the updated section. If flag cleared: mark resolved. If still flagged: run one more section-expander with a refined query (cap: 2 total). If still flagged after 2 attempts: mark as TODO in note; add to task.md.

---

**NEEDS GAP DEPTH**

Determine which of the three dimensions (workaround effort, gap type, closure trajectory) is missing.

Dispatch **section-expander** with:
- `section_text`, `flag_type` = `NEEDS GAP DEPTH`, `note_path` (absolute)
- Targeted `perplexity_ask` query for the missing dimension only; sonar-pro instruction

After write: re-invoke section-depth-evaluator. If still flagged: mark as TODO in note; add to task.md. (Cap: 1 attempt.)

---

**NEEDS COMPARISON**

Dispatch **section-expander** with:
- `section_text`, `flag_type` = `NEEDS COMPARISON`, `note_path` (absolute)
- `perplexity_ask` query asking what users say about this feature across the top two or three comparable products; sonar-pro instruction

Use CX feedback to determine whether the differentiator holds. Update the section — confirm differentiator with evidence or relabel as table-stakes. After write: re-invoke section-depth-evaluator. If still flagged: mark as TODO; add to task.md. (Cap: 1 attempt.)

---

**NEEDS DIAGRAM**

Inline — no subagent dispatch:
1. Determine diagram type: sequence (for flows/decisions) or component (for structure/relationships).
2. Generate the Mermaid diagram inline and add it to the section.
3. Mark section SUFFICIENT after adding the diagram.
4. If generation fails (insufficient information): add to task.md.

---

**NEEDS CX SECTION**

1. Search the existing note for forum quotes, community patterns, or user-reported feelings.
2. Compose a user experience section from that material; insert before the first feature/architecture section.
3. If insufficient material exists in the note: dispatch **section-expander** with a targeted `perplexity_ask` query for user experience reports; sonar-pro instruction. After write: re-invoke section-depth-evaluator. If still flagged: mark as TODO; add to task.md. (Cap: 1 expansion attempt.)

---

**NEEDS DISAMBIGUATION**

Inline — no subagent dispatch:
1. Add a concise clarification immediately after the claim — use a prose sentence, a callout, or a comparison table.
2. Do not create a new top-level section unless the confusion warrants dedicated treatment.
3. If the disambiguation requires domain knowledge that cannot be reliably determined: add to task.md as an open question.

---

**NEEDS GROUNDING**

Inline — no subagent dispatch (may route to NEEDS EXPANSION):
1. Write one mechanism sentence inline explaining why the claim is true.
2. Add a `[[#Section]]` link to the section that contains the full explanation.
3. If no section delivers the mechanism: expand the most relevant section using the NEEDS EXPANSION repair, then add the link.
4. Do not duplicate content — the inline sentence is a pointer, not a replacement for the linked section.

---

**NEEDS REQUIREMENTS COVERAGE**

Dispatch **section-expander** with:
- `section_text`, `flag_type` = `NEEDS REQUIREMENTS COVERAGE`, `note_path` (absolute)
- Targeted `perplexity_ask` query to answer the specific requirement; sonar-pro instruction

After write: add content to the most relevant section. If still unanswered: add to task.md as open question with "(requirement unmet)" marker. (Cap: 1 attempt.)

---

**NEEDS ACTION ITEM**

Inline — no subagent dispatch:
1. If the action item can be inferred from existing note content: add it to task.md directly.
2. If it requires further research: add it to task.md as an open question.

---

## Stage 6 — Source validation + report

**Goal**: Validate source claims; produce consolidated inline report.

### Source validation

**Dispatch**: agent dispatch — source-validator

Collect all `NEEDS SOURCE VALIDATION` claims (extracted during Stage 4). Dispatch **source-validator** (see Subagent Contracts) with:
- `note_path` (absolute)
- List of `{ claim_text, query }` pairs

For each verdict:
- `VALID`: add citation as footnote; remove flag.
- `UNVERIFIABLE`: add "(unverified, direction only)" inline; add claim to task.md.
- `CONTRADICTED`: flag inline; add to task.md for human review.

### Report assembly

**Dispatch**: inline

Assemble and output the inline report:
1. List every section that was expanded and what was added.
2. List every flag that was raised and its resolution (expanded / added to task.md / diagram added / qualifier added / TODO marked).
3. List every item deferred to task.md.
4. If requirements coverage stages were skipped: include the `requirements_skip_reason`.
5. If coverage verdicts were unvalidated (validator returned empty): include the unvalidated warning.
6. If global expansion cap was reached: list sections that were not processed due to cap.
7. Do not append a Verification block — report inline only.

**Produces**: inline report to user

---

## What this is NOT

- Not fact-checking — trust all Perplexity-sourced content
- Not citation counting — sources are already handled by verify-format
- Not a pass/fail gate — it is an iterative improvement loop with per-flag caps and a global session cap
