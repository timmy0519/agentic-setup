---
name: Team decomposition must be coherent
id: team-design-coherence
description: 'A team decomposition must produce roles that are individually coherent (right-sized, non-trivial, domain-focused) and collectively complete (no relay nodes, no orphaned handoffs, no premature lifecycle termination). Each smell is an illustration of incoherence — the principle applies beyond listed cases.'
applies_to:
  doctype: [spec-design]
  stage: [write, verify]
severity: advisory
model_hint: opus
inputs: [artifact]
constituent_checks: [hub-and-spoke, over-specialization, cognitive-overload, missing-peer-loops, gate-inflation, premature-domain-expert-shutdown, manager-as-relay]
---

## Evaluation prompt

A team decomposition must produce roles that are individually coherent (right-sized, non-trivial, domain-focused) and collectively complete (no relay nodes, no orphaned handoffs, no premature lifecycle termination).

**Illustrations of this principle** (non-exhaustive — apply the principle even to cases not listed here):

- **hub-and-spoke**: Any peer handoff routed through the lead without explicit escalation justification. Peers should communicate directly when their work is adjacent; the lead is an escalation path, not a relay.

- **over-specialization**: A role owns a single trivial step that could merge with an adjacent role. Every role must carry enough distinct responsibility to justify its spawn and context cost.

- **cognitive-overload**: A single role spans unrelated domains or more than 5 distinct responsibilities. Split when a role would need expertise in fundamentally different areas to execute well.

- **missing-peer-loops**: A multi-role decomposition with zero peer handoffs (unless it is a single-role delegation). If roles never interact, either they are independent tasks (not a team) or the decomposition missed a collaboration point.

- **gate-inflation**: A gate that is clearly a rubber-stamp with no escalation rationale. Every gate must have a meaningful criterion that could cause rejection; otherwise it adds latency without value.

- **premature-domain-expert-shutdown**: An artifact owner shuts down before all consumers of that artifact have completed, with no clarification channel (standby, memo, or respawn path). Consumers lose access to the authoritative source.

- **manager-as-relay**: A role classified as "manager" whose only function is passing output between specialists with no transformation, judgment, or routing logic. This is a relay node that adds latency. (Overlaps hub-and-spoke when the relay is the lead.)

For each violation found:
1. Name which illustration (or novel case) it falls under
2. Quote the exact text and line number
3. State why it violates the principle
4. Suggest a concrete fix

If no violations are found, state PASS.
If one or more violations are found, state FAIL with all occurrences listed.

## Boundary examples

**PASS:** "Lead delegates domain analysis to researcher and implementation to builder. Researcher sends findings directly to builder via SendMessage. Lead only intervenes on scope disputes." — Direct peer handoff, no relay, right-sized roles.

**PASS:** "Single-role delegation: lead spawns one specialist for the entire task." — No peer loops expected when there is only one role.

**FAIL:** "Researcher sends findings to lead, who forwards them verbatim to builder." — Manager-as-relay; researcher should send directly to builder.

**FAIL:** "Role A: read the config file. Role B: validate the config. Role C: write the output." — Over-specialization; A and B are trivial steps that should merge.

**FAIL:** "Domain expert produces the schema in Stage 2, shuts down at Stage 3 start. Builder needs schema clarification at Stage 4 but expert is gone with no memo or respawn." — Premature shutdown without clarification channel.
