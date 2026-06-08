## Compiler Worker Protocol

This document describes how the verify compiler operates when spawned as a single-correction worker (e.g., by flag-imp Stage 3c). This is NOT a compile.py flag — it's the behavioral protocol for the compiler agent when processing one correction at a time.

---

### Input

Received via agent prompt or SendMessage from the caller (flag-imp, or any other correction source):

| Field | Type | Description |
|-------|------|-------------|
| `correction_type` | `false_positive` \| `false_negative` \| `inconsistency` | What kind of correction |
| `rule_id` | string \| null | Existing rule that fired (null for FN with no rule) |
| `principle_violated` | string | Inferred by caller — the general principle |
| `evidence` | string | What actually happened — specific text/context |
| `artifact_path` | string | File being verified |
| `artifact_type` | `requirements` \| `design` \| `task` \| `other` | Artifact classification |

---

### Process

#### Step 1: Read all principle rules

Read all rule files from `rules/general/` (the 12 principle rules + 3 coverage checks). Build an in-memory index of: `{id, name, statement/description, constituent_checks}`.

#### Step 2: AI judgment — map to existing principle

Determine whether this correction maps to an existing principle rule:
- Read the `principle_violated` field from the input
- Compare against each principle's statement and constituent checks
- A match means: the correction is an instance of an existing principle (even if not explicitly listed in its constituent checks)

#### Step 3: Route by correction_type + overlap

| correction_type | Maps to existing rule? | Action |
|----------------|----------------------|--------|
| `false_positive` | Yes | **Tighten boundary** — add a PASS boundary example from the evidence to the matched rule's `## Boundary examples` section |
| `false_negative` | Yes | **Extend rule** — add a new illustration to the matched rule's constituent checks list, OR write an overlay in `rules/overlays/{domain}/` if the extension is domain-specific |
| `false_negative` | No + quality judgment | **Create new principle** — write a new principle rule file in `rules/general/` following the principle template format |
| `false_negative` | No + mechanical check | **PUSHBACK** — this is a mechanical check, not a principle. Return PUSHBACK to caller |
| `inconsistency` | Yes | **Rewrite prompt** — rewrite the matched rule's evaluation prompt to resolve the ambiguity that caused inconsistent verdicts |

#### Step 4: Update artifact-config.yaml (if needed)

If a new rule was created (new principle in `rules/general/`):
- Determine which artifact types it applies to
- Add the rule ID to the appropriate `quality` list(s) in `artifact-config.yaml`

#### Step 5: Report result

Return to caller:

```yaml
action: "handled" | "pushback"
detail: "<what was done — e.g., 'added PASS boundary to language-precision', 'created new principle: assumption-context-sensitivity', 'mechanical check — not a principle'>"
rule_id: "<rule that was modified or created>"
files_changed: ["<list of files written>"]
```

---

### Pushback Criterion

**Test: "Can you name the general principle this specializes?"**

- **Yes** → it's quality judgment → compiler handles it
  - Example: "User stories in assumptions sections should allow tentative language" → specializes `language-precision` principle
- **No** → it's mechanical → pushback to caller
  - Example: "Check that every table has a header row" → no general principle, just a format check

The compiler does NOT escalate to user for new principles — it creates them. New principle creation is within the compiler's authority when the correction clearly represents quality judgment that no existing principle covers.

---

### Principle Creation Guidelines

When creating a new principle (FN + no match + quality judgment):

1. The principle statement must be a single sentence without AND
2. It must name the professional discipline that owns it
3. It must cover a CLASS of problems, not one specific symptom
4. Include at least the triggering correction as the first illustration
5. Set `model_hint: sonnet` (default for quality judgment)
6. Set `severity: advisory` unless the caller's evidence suggests blocking severity
7. Add boundary examples: the triggering evidence as a FAIL example, construct a contrasting PASS example
