---
name: Task format checklist
id: task-format
description: Structural format checklist for task.md — checkbox format required, no completed items
applies_to:
  doctype: [spec-task]
  stage: [verify]
severity: blocking
model_hint: haiku
inputs: [artifact]
bundled_checks: [checkbox-format, no-completed-items]
---

## Evaluation prompt

Run each check below against the artifact. Report PASS only if ALL checks pass. Report FAIL listing every failing check with its location.

### Check 1: Checkbox format
Scan all task items in the file. Every task item must use `- [ ]` format. Reject prose todos and numbered lists without checkboxes. Flag as FAIL with location if any non-checkbox task items are found.

### Check 2: No completed items
Scan for any `- [x]` or `- [X]` checked checkbox items in the file. Task files should contain only uncompleted items. Flag as FAIL if any checked items are found.

## Boundary examples

**PASS:** All task items use `- [ ]` format, none are checked.

**FAIL:** File contains `1. Create resolve.py` (numbered, no checkbox) or `- [x] Already done item` (completed item).
