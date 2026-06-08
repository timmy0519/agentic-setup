---
name: Design file inventory coverage
id: design-file-inventory-coverage
description: Every file in design.md's inventory has a corresponding task
applies_to:
  doctype: [spec-design]
  stage: [write, verify]
severity: advisory
model_hint: opus
inputs: [artifact, design]
---

## Evaluation prompt

Read design.md and extract all file paths marked "Create" or "Edit" in the file inventory. For each, verify task.md has at least one task that creates or modifies that file. List any uncovered files as FAIL.
