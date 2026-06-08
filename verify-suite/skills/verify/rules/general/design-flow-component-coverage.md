---
name: Design flow component coverage
id: design-flow-component-coverage
description: Every major component or flow step in design.md has a corresponding task
applies_to:
  doctype: [spec-design]
  stage: [write, verify]
severity: advisory
model_hint: opus
inputs: [artifact, design]
---

## Evaluation prompt

Read design.md's diagrams and component descriptions. Extract every major component or flow step. For each, verify task.md has at least one task that implements it. List any uncovered components as FAIL.
