# adversarial-review

A standalone, generative red-team capability usable on any artifact — spec, design, code, or doc.

## What it is

**Mode-2 generative review.** Where checklist `/verify` confirms an artifact conforms to a known format/rule pack (Mode 1), adversarial-review asks the open-ended question: **"how does this fail relative to its stated intent?"** It is a complement to `/verify`, not a replacement — it finds the failure modes a checklist cannot enumerate in advance.

## How it works

1. **Intent extraction** — derives the artifact's stated purpose so critique is grounded in what it claims to do, not in importing requirements it never made.
2. **Lens dispatch** — spawns 1-3 grounded critic lenses as subagents:
   - **Skeptic** — does it actually hold up? where are the unsupported claims and failure modes?
   - **Architect** — does the structure fit the problem? what breaks under load / at the seams?
   - **Minimalist** — what is ceremony, duplication, or over-engineering that could be cut?
3. **Refute pass** — each lens's findings are challenged to drop weak or speculative critiques before they reach the report.
4. **Synthesis** — a severity-rated **advisory** report. It is a **soft-gate**: it surfaces concerns and recommendations but **never auto-blocks** the pipeline.

## Provenance-aware routing (soft)

When the artifact under review carries a task-tool `origin` tag, the reviewer reads it to route lenses appropriately (e.g. spec vs. code vs. doc emphasis). This is a **soft** signal — the plugin works fully without it and degrades gracefully when no `origin` tag is present.

## Relationship to other plugins

- **Depended on by `verify-suite`** — verify-suite invokes this plugin as its Mode-2 generative pass alongside Mode-1 checklist verification. This plugin itself is **standalone with no plugin dependencies** and can be installed and used on its own.

## Contents

| Path | Purpose |
|------|---------|
| `skills/adversarial-review/SKILL.md` | Skill entry point + routing description |
| `skills/adversarial-review/references/reviewer-lenses.md` | Lens definitions (Skeptic / Architect / Minimalist) |
| `skills/adversarial-review/references/reviewer-prompt.md` | Per-lens critic prompt |
| `skills/adversarial-review/references/verdict-format.md` | Severity-rated advisory report format |
| `skills/adversarial-review/references/sop.md` | Full orchestration SOP |
| `agents/adversarial-reviewer.md` | The critic subagent definition |

## Triggers

"red team this", "adversarial review", "stress test this design", "what breaks", "how reliable is this". **Not** a format/conformance checker — that is `/verify`.
