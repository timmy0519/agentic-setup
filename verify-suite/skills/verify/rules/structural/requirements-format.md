---
name: Requirements format checklist
id: requirements-format
description: Structural format checklist for requirements.md — goal statement, user stories, scope sections, constraints
applies_to:
  doctype: [spec-req]
  stage: [verify]
severity: blocking
model_hint: haiku
inputs: [artifact]
bundled_checks: [goal-statement, user-stories-present, user-stories-format, in-out-scope-defined, constraints-listed, provenance-tags]
---

## Evaluation prompt

Run each check below against the artifact. Report PASS only if ALL checks pass. Report FAIL listing every failing check with its location.

### Check 1: Goal statement
Verify the file has a clear one-sentence goal statement near the top (within the first 20 lines or under a "Goal" heading). The goal must be a single declarative sentence stating what the project/feature achieves. Flag as FAIL if missing or if the "goal" is actually a paragraph of context.

### Check 2: User stories present
Verify at least one user story block exists in the file. A user story block contains "As a..." or "I want" or a clearly labeled user story section with at least one item. Flag as FAIL if no user stories found.

### Check 3: User stories format
Verify each user story follows the format: "As a [role], I want [action], so that [benefit]." Both the "I want" and "so that" clauses must be present. Flag each story missing either clause.

### Check 4: In/out scope defined
Verify the file contains both an "In scope" (or "In-scope") section and an "Out of scope" (or "Out-of-scope") section, each with at least one item. Flag as FAIL if either section is missing or empty.

### Check 5: Constraints listed
Verify the file contains a "Constraints" section with at least one constraint listed. Flag as FAIL if the section is missing or empty.

### Check 6: Provenance tags
Verify each user story carries an origin tag marking it user-stated vs AI-derived: `[user]` (the user explicitly asked for it) or `[ai]` (the author inferred or derived it). If the file lists acceptance criteria, each AC carries the same tag. Tag at user-story / AC granularity — NOT every sub-bullet. Flag as FAIL any user story or AC with no origin tag; an untagged item is un-triaged provenance.

Rationale (why this is blocking, not cosmetic): downstream adversarial review routes by origin — `[user]` items get a cost/benefit challenge ("is the user over-scoping their own problem?"), `[ai]` items get a traceability+necessity challenge ("does this map to a real user ask, or is it inferred cruft?"). An untagged item silently loses that routing, so the highest-risk AI-added requirements escape the necessity check.

## Boundary examples

**PASS:** File has "**Goal:** Build a CLI that syncs transactions", 3 user stories each prefixed with `[user]` or `[ai]` and carrying I-want/so-that clauses, In scope and Out of scope sections each with items, and a Constraints section with 2 items.

**FAIL:** File begins with background context paragraphs, has user stories missing "so that" clauses, carries no `[user]`/`[ai]` origin tags on its stories, and no Constraints section.
