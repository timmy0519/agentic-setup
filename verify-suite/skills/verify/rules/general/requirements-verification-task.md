---
name: Requirements verification task
id: requirements-verification-task
description: Last item in immediate section references requirements verification
applies_to:
  doctype: [spec-task]
  stage: [write, verify]
severity: advisory
model_hint: sonnet
inputs: [artifact]
---

## Evaluation prompt

Verify that the last item in the immediate/main task section references verifying against requirements (e.g., "Verify all requirements are met", "Run /verify-requirements", or similar). Flag as FAIL if the task list ends without a verification step.
