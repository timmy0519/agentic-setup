---
name: artifact-flow
description: "[orchestrator] Route a task to its minimum-viable artifact set by task class (1-7), then run a thin per-artifact loop: gather prewrite inputs → writer drafts → reviewer verifies against /verify rule pack → brief user → next. Use when starting any non-trivial work to decide what to produce and how. Trigger phrases: \"how should I shape this work\", \"what artifacts do I need\", \"start a new task\", \"spec this out\". Do NOT trigger for: verify-only (→ /verify), existing-spec-update without re-scoping (→ direct edit), research synthesis only (→ /research-team)."
---

## Purpose

Decide what artifacts a task needs based on task class, then orchestrate writers + reviewers per artifact. Keeps SOP thin by composing existing skills + rule pack + per-doc-type prewrite refs.

## Gates, ACs & review depth

When the task is tracked in task-tool, record an **AC at each review gate** — a pointer to the `/verify` rule that is the gate's standard (not a copied body), tagged `origin: user|ai`. The AC is what makes the gate resumable and self-checking on rework.

**Match review depth to gate stakes — do NOT blindly run the checklist AC.** A plain `/verify` checklist pass is the default and is right for routine gates. Escalate to an **adversarial review** (`adversarial-reviewer` agent; `/adversarial-review` skill for high-stakes) when the gate has any of:

- **Tradeoffs** — the artifact picked among competing options
- **Open-ended** — no single right answer; quality is judgment, not conformance
- **Use-case-dependent** — correctness hinges on context the checklist can't see
- **Over-engineering risk** — could be more complex than the goal needs
- **One-way door** — high cost-of-reversal (schema / auth / db / API-contract picks)

These map to selector **class 6–7**. A checklist confirms "has property X"; adversarial asks "does this actually achieve its intent" — the failure modes a checklist structurally misses. Recording an AC and then rubber-stamping it with a shallow pass is the anti-pattern this guards against.

## I/O Contract

**Inputs:**
- `{task}` — what's being done (one sentence)
- `{class_hint}` (optional) — 1-7 if user already knows; otherwise classify in Stage 1

**Outputs (per artifact in the set):**
- Drafted artifact passing `/verify` rule pack
- User brief after each artifact (1-2 sentences + decisions + go/redirect prompt)

**Artifact set per class** — see `references/selector.md`. Briefly:
- Class 1-2 → plan-mode transcript + PR description
- Class 3 → research note folder (delegates to `/research-team`)
- Class 4+ → spec folder (req → design → task)
- Class 6-7 → spec folder + human-review tier on one-way doors

## Subagents

| Subagent | Stage | Dispatch | Receives | Produces |
|----------|-------|----------|----------|---------|
| prewrite-gatherer | per-artifact | Agent dispatch | `{doctype}`, `{task}`, `references/prewrite/{doctype}.md` path | Answers to prewrite Qs (asks user if gaps) |
| writer | per-artifact | Agent dispatch | `{doctype}`, prewrite answers, `/verify` rule pack path | Drafted artifact path |
| reviewer | per-artifact | Agent dispatch | Artifact path, `/verify` rule pack path | PASS/FAIL + line-anchored rewrites |

## Rule pack reference

Quality bar for all writers + reviewers: `${CLAUDE_PLUGIN_ROOT}/skills/verify/rules/`
- `general/` — cross-artifact rules (incl. `serves-reader-purpose.md`)
- `structural/` — per-doc-type format checks (`requirements-format.md`, `design-format.md`, `task-format.md`)
- `overlays/` — domain overlays (e.g., `overlays/agentic/`)

Writers reference applicable rules during drafting (not just post-hoc).

## Execution

Run the workflow in `references/sop.md`.

## Delegation

For class-3 research notes, delegate end-to-end to `/research-team` rather than re-implementing. For class 4+ spec folders, `artifact-flow` runs the thin loop directly; do NOT call `/spec-authoring` (heavy alternative path — kept for backward compat).
