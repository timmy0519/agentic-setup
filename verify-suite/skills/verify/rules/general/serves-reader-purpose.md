---
name: Sections serve their reader's purpose (translation done)
id: serves-reader-purpose
description: |
  Writer translates FROM "what was researched / decided / proposed" TO "what the reader takes away AND how it applies to them." Reader does not decode abstraction into their case; writer does the rendering. Tier 1 bedrock; Tier 2 cross-cutting instances; Tier 3 section-specific failure modes. Read in tier order — Tier 1 first.
applies_to:
  doctype: [research-note, spec-req, spec-design, spec-task, brief, memory, verify-rule, claude-md]
  stage: [write, verify]
severity: blocking
model_hint: sonnet
inputs: [artifact]
constituent_checks: [translation-done, top-to-bottom-takeaway, reader-purpose-per-section, inverted-pyramid, first-pass-comprehensibility, bluf-problem-first, concise-concrete-opening, no-process-internal-language]
---

## Evaluation prompt

For human-reviewed artifacts (PRD, design doc, brief, plan, post-mortem, research note), apply checks in **TIER ORDER**. Tier 1 is bedrock — Tier 2 and Tier 3 are instances of Tier 1 failing in specific ways. Internalize Tier 1 first; the rest derive from it.

SKIP when artifact is AI-only consumption (raw pipeline trace, log file, internal diff) — flag the SKIP reason.

---

## Tier 1 — Bedrock (apply FIRST)

**translation-done**: The writer must translate FROM "what was researched, decided, or proposed" TO "what this reader takes away AND how it applies to their case." Reader does not decode abstraction into their case; writer does the rendering.

Required:

- **(a) Named audience** or strong implication. If audience or applicability is unknown when the artifact is written, the writer must ASK or GATHER from existing docs / project context BEFORE drafting. Drafting against an imagined usecase is a violation.
- **(b) Takeaway stated explicitly** for the named audience — not buried in abstraction the reader must decode.
- **(c) Translation rendered appropriately for artifact purpose**:
  - **Entry brief** → named pointers + decisions inline so reader can self-serve to the right sibling for their question.
  - **Research synthesis** → worked examples + action paths per identified usecase.
  - **Design doc** → implementation outline + reviewer's likely concerns addressed inline.
  - **Plan** → stepwise action items + ownership.
  - **Brief** → bottom-line recommendation + "you should do X."
  - **Post-mortem** → preventions + owners.
  - **Reference** (API / schema / glossary) → SKIP this check; mechanism IS audience match.

If Tier 1 fails, the artifact fails — Tier 2 and 3 are instances of where translation manifests. Fix Tier 1 first; don't bury Tier 1 failure in per-section Tier 2/3 verdicts.

---

## Tier 2 — Cross-cutting instances (apply if Tier 1 passes)

These apply ACROSS sections — they are how translation manifests at the artifact level.

**top-to-bottom-takeaway** (whole-artifact pass — apply ONCE at end): Sections read in declared order, by a senior unfamiliar with the artifact, yield the writer's intended message. Alternative read paths (e.g., "skip to §3 if X") stated explicitly at top. This is the translation-success verification.

**reader-purpose-per-section**: Each section's first paragraph implicitly or explicitly tells the reader what they learn or do there. Sections that read like author notes flagged.

**inverted-pyramid**: Most-important content first within the section; supporting evidence / detail / citations deferred to appendix or sibling files. Priority order matches the reader's, not the writer's investigation order.

**first-pass-comprehensibility**: Load-bearing claims parseable on first pass without opening a sibling file. Cross-references to siblings carry detail, not the load-bearing claim itself.

---

## Tier 3 — Section-specific instances (apply within named section types)

Concrete patterns where translation commonly fails. Catch these to surface the bedrock failure earlier.

**bluf-problem-first**: TL;DR / lede states the problem (or canonical reader entrypoint) AND the bottom-line thesis or recommendation in the first 1-2 sentences. Mechanism-first fails this. Exception: API reference, runbook, schema doc, glossary — lead with canonical reader entrypoint. Exception does NOT apply to research brief, PRD, design doc, entry overview, post-mortem, plan.

**concise-concrete-opening**: Opening sentences avoid long noun-chains, abstract phrasing, passive constructions, packed enumerations (≥3 mechanism items before the thesis is stated), and insider jargon not introduced in the artifact.

**no-process-internal-language**: The artifact shows the reader the CONTENT, not the AUTHOR'S WORKFLOW. Forbidden: "Round 1 established / round 2 zoomed out…", "this pipeline first…", "the synthesis-writer chose…", "after research-round-N…", references to research arc, draft iteration counts, internal review process.

---

## Positive-pattern references

Cite known-good shapes alongside violations to give writers targets, not just fences:

- **Trigger-phrase pointer** ("X? → file.md") satisfies reader-purpose with minimum mechanism.
- **Diagram + reader-question table** for entry-brief navigation satisfies inverted-pyramid + reader-purpose simultaneously (matklad README→ARCHITECTURE convention).
- **Decision → rationale → pointer** sentence structure satisfies inverted-pyramid within Major-decisions sections.
- **Problem → thesis → mechanism → pointer** sentence order in TL;DR satisfies bluf-problem-first + inverted-pyramid + first-pass-comprehensibility.
- **Confidence-banded layer table** (Layer | Confidence | Anchor) satisfies status-block contract with minimum mechanism.
- **Audit-shape 6+1 fields** (in-scope/out, decisions inline, alternatives, open questions, focused content, status block, conditional diagram) satisfies post-YOLO audit-surface contract.
- **Per-usecase worked example** (named usecase → task class → pattern set → before/after → action items) satisfies translation-done for research-synthesis artifacts.

---

## Output

For each violation:
1. **Tier** of the failing check (T1 / T2 / T3).
2. **Constituent check name**.
3. Quote exact text + line number.
4. Why it violates the check.
5. Concrete fix suggestion.
6. If a positive-pattern reference would have prevented it, name the shape.

**Tier 1 (translation-done) failure ALWAYS surfaces FIRST** — never bury it in per-section verdicts.

Then per-section verdicts (PASS / CONSIDER / FAIL / SKIP) for Tier 2 / 3 checks.
Then whole-artifact verdict with Tier 1 + top-to-bottom-takeaway evaluated.

---

## Boundary examples

**PASS:** TL;DR opening: *"Teams shipping under YOLO have no shape for the post-hoc artifact. This brief recommends a pattern catalog plus one specific composition for class-4+ tasks. Detail in named-pointer siblings below."* — states problem (sentence 1), thesis (sentence 2), pointer (sentence 3). Uses Problem → thesis → mechanism → pointer shape.

**FAIL (Tier 3 — mechanism-first):** *"Progressive spec review is a sequential stage-gated pipeline (PRD → Requirements → Design → Plan/task) with a per-stage AC rule library, a first-class `recycle` back-edge (Cooper stage-gate naming), and cross-stage `inputs:` resolved via Bazel/Contingent three-case semantics."* — packs ≥4 mechanism items before stating problem or thesis. Violates bluf-problem-first + concise-concrete-opening. Tier 1 implication: writer is dumping mechanism without translating to reader's question.

**FAIL (Tier 3 — process-internal):** *"Round 1 establishes the pipeline architecture and shows it borrows `/verify` whole-cloth at Rung 1; round 2 zooms out to the reusable layer beneath…"* — leaks author's research arc. Reader does not care about authoring rounds. Tier 1 implication: writer translated the workflow, not the content.

**FAIL (Tier 1 — translation absent):** A research synthesis listing 10 patterns with definitions but no usecase-applied examples. Reader cannot reason about "does this apply to my case?" Violates translation-done(c) — research-synthesis purpose requires worked examples + action paths per usecase.

**CONSIDER (jargon density):** Major-decisions bullet referencing "Bazel/Contingent three-case semantics," "Cooper stage-gate's gate-outcome," without introducing terms — acceptable shorthand for named audience but at the edge of first-pass-comprehensibility. Flag for review; not blocking.
