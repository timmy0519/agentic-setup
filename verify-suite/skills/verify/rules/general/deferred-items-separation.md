---
name: Deferred items separation
id: deferred-items-separation
description: Deferred items appear in a distinct section, not mixed with immediate
  tasks
applies_to:
  doctype: [spec-task, wishlist]
  stage: [write, verify]
severity: advisory
model_hint: sonnet
inputs: [artifact]
---

## Evaluation prompt

Verify that deferred or future-phase items are in their own section (e.g., "Deferred", "Future", "Phase 2"), not mixed into the immediate task list. Flag as FAIL if deferred items appear alongside immediate tasks without section separation.
