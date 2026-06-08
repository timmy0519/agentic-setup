## Adversarial Review — SOP

Generative, intent-grounded red-team of an artifact. The orchestrator (you) extracts intent, dispatches independent critic lenses as subagents, runs a refute pass to kill false positives, and synthesizes a severity-rated **advisory** report. This is **Mode 2** of verification — complementary to the checklist conformance pass (`/verify`), not a replacement. It is **read-only**: it identifies problems, never applies fixes.

**This skill is the high-stakes escalation. The default is the `adversarial-reviewer` agent** — a single agent holding all lenses in one context, which shares grounding and self-dedupes (cheaper, no cross-lens overlap). Reach for THIS parallel multi-lens skill only when the artifact is high-stakes enough that independent reviewers (no same-context bias, diverse pressure) are worth the ~3× cost and the mandatory dedup it forces. If you run the parallel version, the refute + dedupe pass (Step 4) is NOT optional — independent lenses WILL overlap (e.g. correctness and structure both flag a concurrency claim), and raw un-deduped lens output over-reports.

**Adversarial review is a SAMPLING process — one pass is not exhaustive.** Empirically, two independent passes over the same artifact find largely DIFFERENT real defects (high precision, partial + non-overlapping recall). So:
- **Default = one pass** — a good, cheap signal. Treat its output as "found these," never "these are all there are."
- **High-stakes = N independent passes, then UNION** — run this multi-lens skill, OR simply run the single agent 2–3 times with fresh context, and merge the deduped findings. The recall gain comes from *independent samples*, not only from lens-diversity — even repeated identical-prompt runs raise recall. Do not present a single pass as a complete audit.
- Each pass still has its own calibration error to watch: a pass may severity-inflate impl-detail the scope deferred, OR flag not-yet-implemented source as a design defect (reviewing the wrong layer). The classification step (DEFECT/SCOPE/DEFERRED) and judging against the DESIGN's claims — not the unmodified source — control both.

> Logic adapted from `poteto/noodle` (MIT) `adversarial-review`. Customized: grounding source is the consuming project's requirements/decisions/`/verify` rule-pack (not `brain/principles.md`); lenses run as Agent subagents (not cross-model CLI); output maps to a soft-gate advisory report.

---

## I/O Contract

**Inputs:**

| Parameter | Required | Default |
|-----------|----------|---------|
| `artifact_path` | yes | — |
| `grounding` | no | auto-discover (see Step 1) |
| `lenses` | no | auto-select by size/risk (Step 2) |
| `cross_model` | no | false (Claude subagents); true spawns reviewers on an opposing-model CLI if available |

**Output:** an advisory report (chat + optional file) — confirmed findings (severity + cited span + violated requirement + failure scenario), rejected-as-false-positive items with reasons, per-area reliability ratings, and graduate-to-rule candidates. **Never auto-blocks** — the lead decides; any override of a high-severity finding is recorded with a reason.

---

## Why this exists (do not collapse into /verify)

Checklist `/verify` asks "does the artifact have property X?" — conformance. It cannot find failure modes nobody has codified yet, and writer-self-verify systematically misses what the writer didn't think to check (over-engineering, unimplementable claims, ungrounded edge cases). This skill is the generative complement: it tries to BREAK the artifact against its own stated intent. Recurring findings graduate into checklist rules, so the cheap conformance pass absorbs them over time.

---

## Procedure (5 steps)

### Step 1 — Load grounding (intent + principles)

The adversary must be grounded in the artifact's source-of-truth, or it invents strawmen. Assemble the grounding set:

1. If `artifact_path` is inside a spec folder: read sibling `requirements.md`, `design.md`, `.decisions.md` that exist.
2. Read the relevant rule files for the artifact's doctype from the verify-suite `/verify` rule pack — these encode known-failure principles.
3. If no grounding is discoverable and none supplied: state the artifact's apparent intent and **confirm it with the user** before reviewing (a review with the wrong intent is noise).

Record the grounding set; it is passed verbatim to every lens.

### Step 2 — State intent + select lenses

1. Write one explicit sentence: "This artifact's intended goal is X." (Pulled from grounding, not invented.)
2. Size/risk → lens count (mirrors noodle):
   - Small / low-risk → 1 lens (**Skeptic**)
   - Medium → 2 (**Skeptic + Architect**)
   - Large / high-risk / irreversible → 3 (**Skeptic + Architect + Minimalist**)
3. Add a doctype lens when warranted: **Security** for code/auth/data-handling; the Architect lens already covers implementability for specs/designs.

Lens definitions: `references/reviewer-lenses.md`.

### Step 3 — Spawn lenses in parallel (Agent dispatch)

Dispatch one subagent per selected lens, concurrently. Each receives the dispatch template in `references/reviewer-prompt.md`, filled with: the stated intent, the assigned lens (verbatim), the grounding set (verbatim — not summarized), and the artifact.

**Grounding discipline (the false-positive control — non-negotiable):** every finding MUST cite an exact span in the artifact AND the requirement/principle it violates. A finding without both is dropped as unsupported. Each finding carries a severity: **high** (blocks ship), **medium** (should fix), **low** (worth noting).

For `cross_model: true`, spawn each reviewer on an opposing-model CLI instead of a subagent (kills same-model bias) — only if that CLI is available; otherwise fall back to subagents and note it.

### Step 4 — Refute pass + synthesize

1. **Refute (skeptic counter-pass):** for each finding, check whether it survives — does the cited span actually say what the finding claims? Is the violated requirement real? Drop findings that are unsupported, mis-cited, or contradicted by the grounding. (For high-stakes artifacts, dispatch a dedicated refuter subagent per finding instead of inline judgment.)
2. **Dedupe:** merge overlapping findings across lenses into one entry each.
3. Produce a single consolidated finding set.

### Step 5 — Lead judgment + advisory report

Apply your own analysis using intent + grounding as the frame. For each surviving finding: accept or reject with a one-line reason (explicitly call out overreach). **Classify each finding** (fixes severity calibration):
- **DEFECT** — violates a requirement/decision/claim the artifact actually states. Severity as warranted.
- **SCOPE** — underspecified AND the artifact's scope section doesn't say in/deferred/out → a challenge to the SCOPE STATEMENT, not a broken claim; do not inflate to HIGH.
- **DEFERRED** — scope explicitly defers/excludes it → down-rate to LOW/note-only (if you think the deferral is wrong, raise it as a STRATEGY recommendation instead).

Then emit the report (format: `references/verdict-format.md`):

- **Confirmed findings** — class (DEFECT/SCOPE/DEFERRED), severity, cited span, violated/underspecified requirement, concrete failure scenario.
- **Reliability ratings** — per major area/requirement: HIGH/MEDIUM/LOW, with the reasoning (rate even where COVERED — "covered but fragile because…").
- **Strategy recommendations (advisory — take or leave)** — challenges to the intent/frame itself: internal inconsistency in the goal, or a simpler/more durable approach for this purpose or a likely future need. Surface them; the user decides. Keep separate from defects.
- **Scope clarity** — is the artifact's in/out/deferred scope crisp enough to judge against? Fuzzy scope is itself a finding (it's why SCOPE-class items exist).
- **Rejected as false-positive** — finding + why dropped (keeps the adversary honest, builds the false-positive catalog).
- **Graduate candidates** — findings of a class likely to recur → flag for codification as a `/verify` checklist rule (route via `/flag-imp`).

The report is **advisory**. It does not gate automatically; the lead/user decides what to act on. If acting inside a workflow with a soft gate, a decision to ship past a high-severity finding is recorded with a reason.

---

## Constraints

- Read-only on the artifact — never edit or "fix" during review.
- Every finding cites span + violated requirement, or it is dropped.
- Lenses are independent — do not let one lens's output bias another (parallel dispatch, separate contexts).
- Advisory, not blocking — prefer a strong-default soft-gate (with audited override) over a hard refusal.
- Single user surface — subagent lenses return findings to the orchestrator; the orchestrator presents one synthesized report.
- Prototype scope: measure false-positive rate before promoting lenses to `.claude/agents/` or wiring as `/verify --adversarial` Mode 2.
