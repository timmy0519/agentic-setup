---
name: Design format checklist
id: design-format
description: Structural format checklist for design.md — file path inventory present, at least one Mermaid diagram present
applies_to:
  doctype: [spec-design]
  stage: [verify]
severity: blocking
model_hint: haiku
inputs: [artifact]
bundled_checks: [file-path-inventory, mermaid-diagram-present]
---

## Evaluation prompt

Run each check below against the artifact. Report PASS only if ALL checks pass. Report FAIL listing every failing check with its location.

### Check 1: File path inventory
Verify the design file contains at least one file path inventory — a list of concrete file paths for files to be created or modified. This can be in a table, bullet list, or dedicated section. Flag as FAIL if no concrete file paths are listed.

### Check 2: Mermaid diagram present
Verify the design file contains at least one Mermaid diagram (a fenced code block with language identifier `mermaid`). At minimum, one architecture or flow diagram is required. Flag as FAIL if no Mermaid diagram is found.

## Boundary examples

**PASS:** Design has a "File inventory" table listing 5 file paths with Create/Edit actions, and a `mermaid` sequence diagram showing the main flow.

**FAIL:** Design describes components in prose but lists no concrete file paths and has no diagrams.
