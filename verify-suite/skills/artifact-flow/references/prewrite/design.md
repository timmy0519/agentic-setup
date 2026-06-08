## Prewrite — design.md (class 4+)

Purpose: gather architecture framing before drafting design. Architect tier — analyze target architecture, prefer borrowed mechanisms.

### Required inputs (block until answered)

1. **Requirements satisfied** — cross-ref requirements.md in-scope items; every in-scope item must map to a design component.
2. **Reuse vs net-new** — what existing infra / primitives / OSS patterns can this borrow? Borrow mechanisms rather than redesigning them, and treat an OSS pre-fetch as the validation gate for any "borrow from X" claim. List candidate-reuse before proposing net-new.
3. **Major decisions** — where do multiple plausible options exist? These need research-grounding before the user is asked. Frame each as concrete options + tradeoffs + recommendation.
4. **Door tag per decision** — one-way (high cost-of-reversal) or two-way? Drives review modality and class-6 vs class-4 promotion.
5. **Failure modes** — what fails inline? Address via the design-defensibility 3-check rubric (failure-mode reality, OSS-citation existence, writer-authority feasibility).
6. **File/path inventory** — every file the design touches, with one-line role.

### Best-practice references

- Rule pack: `data-flow-consistency`, `design-economy`, `design-extensibility`, `design-file-inventory-coverage`, `decisions-justified`, `design-format` (in the verify-suite `/verify` rule pack).

### Anti-patterns to flag during prewrite

- Redesigning what OSS / existing primitives already solve — borrow first, justify net-new explicitly.
- Dumping implementation detail (prompts, thresholds, line-level logic) — that belongs in code, not design.
- User stories in design.md — those live in requirements.md.
- Strawman "Rejected: X" foils that weren't actually advocated.

### Output (writer consumes)

- `requirements_map`: dict[req_id → component]
- `reuse_targets`: list[{primitive: str, source: str}]
- `net_new`: list[{component: str, justification: str}]
- `decisions`: list[{question: str, options: list, picked: str, door: one-way|two-way, rationale: str}]
- `failure_modes`: list[{mode: str, mitigation: str}]
- `file_inventory`: list[{path: str, role: str}]
