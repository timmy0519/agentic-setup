## Reviewer Lenses

Each lens is an independent adversarial persona. One subagent per selected lens. A lens challenges whether the artifact achieves its **stated intent** — it never redesigns the intent itself. Findings ground in the grounding set (requirements / decisions / `/verify` rules), not personal taste.

Adapted from `poteto/noodle` reviewer-lenses (Skeptic / Architect / Minimalist); Security added for code/data artifacts.

---

### Skeptic — correctness & failure modes

Probes: "What inputs, states, or sequences break this? What error paths are unhandled or silently swallowed?"

Looks for:
- Edge cases and boundary conditions not covered.
- Race conditions, concurrency hazards, ordering assumptions, non-atomic multi-step operations.
- Claims asserted but not proven; "works" that is environment-specific rather than genuinely verified.
- Failure paths that trap the caller (errors where a graceful result was needed) or silently lose data.

### Architect — structure, coupling, scale

Probes: "Does the structure actually meet the stated objectives? What couples that shouldn't? What breaks at scale or under concurrency?"

Looks for:
- Coupling and boundary violations; a component reaching across a boundary it shouldn't.
- Assumptions about scale, load, or concurrency that fail in practice.
- Implementability gaps — design claims that the named mechanism/source cannot actually support (check against real source when available).
- Contracts that block evolution (no migration path, hardcoded version, name collisions).

### Minimalist — simplicity & essential complexity

Probes: "What can be deleted without losing the stated goal? Is this complexity *essential* to the problem or *accidental*? Knowing everything we know now, is there a fundamentally simpler **shape** that meets the same goal — and would a POC covering the high-value 80% at a fraction of the cost be the better first build?"

Looks for:
- Single-use abstractions, speculative flexibility with no concrete justification.
- Scope creep / over-engineering beyond the stated intent; **accidental complexity a different decomposition would dissolve**.
- A materially simpler overall **design/shape** for the same goal — not just local deletion, but "what is the clean solution knowing what we know now?" (CLAUDE.md's *is there a simpler, more coherent shape?* test).
- Over-building ahead of proven need: where a **thin POC/MVP** would validate the core and cover most requirements before committing to the full build.
- Duplicate mechanisms where an existing one was already available (reuse missed).
- Parts whose removal would not harm the stated goal.

### Strategist — challenge the frame (advisory)

Probes: "Is the stated intent itself sound? Is there a simpler or more durable approach that serves this purpose — or a likely future need — better than what's proposed?"

Looks for:
- Internal inconsistency in the goal/intent itself (the artifact faithfully serves an intent that contradicts itself or another stated goal).
- A materially simpler or more robust approach to the SAME purpose that the artifact didn't consider.
- **Requirement cost/benefit**: a stated requirement that drives disproportionate complexity for marginal value — recommend dropping, deferring, or relaxing it. (This questions the requirement *set* itself, so it is a recommendation, never a defect.)
- Future-fit: a near-term need the current frame will block or force a rewrite for.

Output is **advisory recommendations** — the caller takes or leaves them. This lens is allowed to question the intent (unlike the others, which judge achievement OF the intent). Keep its output clearly separate from defects so it never blocks on a matter of strategy.

### Security (code / auth / data-handling artifacts only)

Probes: "How is this abused? What trust boundary is crossed?"

Looks for:
- Unvalidated input, injection surfaces, secrets handling, authz/authn gaps.
- Trust assumptions about callers, tools, or external data that don't hold.
- Sensitive-data exposure paths (logs, error messages, persistence).

---

**Provenance routing** (when items carry `origin: user|ai` tags, e.g. task-tool ACs): origin is not a suspicion flag — it selects the lens. `origin: user` → Strategist (is the user over-scoping their own problem? worth the cost? — advisory). `origin: ai` → Minimalist + traceability (does it map to a real user ask, or inferred cruft? necessary?). Both audited, neither exempt; the lens differs.

**Lens selection** (per SOP Step 2): small/low-risk → Skeptic only; medium → + Architect; large/high-risk → + Minimalist. Also add **Minimalist whenever the artifact proposes a NEW mechanism or non-trivial build** (over-engineering risk lives there, not only in large artifacts). Add Security for code/auth/data; add Strategist when the artifact's intent/approach/requirement-set is itself worth challenging (new designs, high-stakes direction calls, suspected over-scoped requirements). The Architect lens carries implementability for specs/designs.
