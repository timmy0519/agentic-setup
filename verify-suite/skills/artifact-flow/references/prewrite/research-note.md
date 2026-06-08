## Prewrite — research-note (class 3)

Purpose: gather framing before delegating to `/research-team` (or running synthesis directly). Most class-3 work delegates end-to-end; this prewrite is the dispatch-decision context.

### Required inputs (block until answered)

1. **Question** — what is the user actually trying to answer? (one sentence, falsifiable).
2. **Shape** — comparative (tools/options/tradeoffs) vs principle-finding (patterns/conventions) vs walkthrough (how-to-do-X process)?
3. **Vault coverage check** — run your vault / knowledge-base search (if available) for adjacent ground BEFORE external search. Surface: existing notes + gap.
4. **Audience** — future self / future agent session / external reader? (drives format depth).
5. **Decision-grounding vs intuition-building** — does this inform a near-term decision, or build general understanding? (decision ⇒ tighter scope + status block of confidence; intuition ⇒ broader, more analogy).

### Best-practice references

- Rule pack: `serves-reader-purpose` (Tier 1 translation-done is critical), `uncertainty-managed` (in the verify-suite `/verify` rule pack).
- Guidance: catalog interaction patterns, not artifact types; process topics need a stage-by-stage walkthrough; tool research → pattern decomposition + adoption ladder.
- Sibling SOP: `/research-team` (preferred dispatch path).

### Anti-patterns to flag during prewrite

- Researching ground the vault already covers — surface existing note and confirm gap before proceeding.
- Producing a product tour when the user wants a selector.
- Cataloguing artifact *types* when user wants interaction *patterns*.

### Output (writer / `/research-team` consumes)

- `question`: str
- `shape`: comparative | principle | walkthrough
- `vault_gap`: {existing: list[path], missing: str}
- `audience`: self | agent | external
- `decision_or_intuition`: decision | intuition
- `dispatch`: research-team | inline (default: research-team)
