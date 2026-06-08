---
name: Requirements coverage
id: requirements-coverage
description: Every user story and in-scope item is addressed in the artifact
applies_to:
  doctype: [spec-design]
  stage: [write, verify]
severity: blocking
model_hint: opus
inputs: [artifact, requirements]
---

## Evaluation prompt

Read requirements.md and extract all user stories and in-scope items. For each, verify the current artifact addresses it — design.md should have components/flows covering it, task.md should have tasks implementing it. List any unaddressed requirement as a FAIL.
