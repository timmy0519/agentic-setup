---
name: adversarial-review
description: "[orchestrator] Adversarial 'how does this fail vs its stated intent' review of an artifact (spec, design, code, doc). Generative red-team that COMPLEMENTS checklist /verify — extracts intent, spawns 1-3 grounded critic lenses (Skeptic/Architect/Minimalist), runs a refute pass, synthesizes a severity-rated ADVISORY report (soft-gate, never auto-blocks). Use for 'red team this', 'adversarial review', 'stress test this design', 'what breaks', 'how reliable is this'. NOT a format/conformance checker — that is /verify."
---

Run the adversarial-review workflow defined in `references/sop.md`.

Prototype (v0). Logic adapted from the MIT-licensed `poteto/noodle` adversarial-review skill; only the IO/grounding layer is customized for your project. See `references/sop.md` for the 5-step procedure, `references/reviewer-lenses.md` for the critic lenses, and `references/reviewer-prompt.md` for the per-lens dispatch template.
