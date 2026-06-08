## Prewrite — task.md (class 4+)

Purpose: gather coverage framing before drafting task list. Task = checkbox per file in design inventory + per major flow component + phased test cases.

### Required inputs (block until answered)

1. **File inventory from design** — every file in design.md's inventory needs a corresponding task (per `general/design-file-inventory-coverage.md`).
2. **Major flow components** — each component in the design diagram needs a task (build / wire / verify).
3. **Phased test cases** — sanity → happy path → per-user-story → edge. Define coverage per phase, not just impl steps.
4. **Open questions to surface vs deferred** — questions blocking task execution get surfaced to the user now; non-blocking go to a "Deferred" section (keep deferred-but-in-scope separate from excluded).
5. **Verification mapping** — each user story from requirements maps to one or more verification tasks (per `general/requirements-verification-task.md`).

### Best-practice references

- Rule pack: `concrete-action-verbs`, `deferred-items-separation`, `requirements-verification-task`, `design-file-inventory-coverage`, `task-format` (in the verify-suite `/verify` rule pack).
- Sibling SOP: task-tool MCP (`mcp__task-tool__init`) for structured tracking of phased test progression.

### Anti-patterns to flag during prewrite

- Narrative prose instead of checkboxes — task.md is a list, not a story.
- Including completed items (those live in commit history / status block, not the active task list).
- Implementation detail in task descriptions (mechanism belongs in design.md; tasks reference "what" and "verify", not "how").
- Vague action verbs ("handle X", "support Y") — use concrete verbs per the rule.

### Output (writer consumes)

- `file_tasks`: list[{path: str, verb: str, dependency: list[str]}] (one per design inventory entry)
- `component_tasks`: list[{component: str, verb: str}] (one per flow component)
- `test_phases`: {sanity: list, happy: list, per_us: dict[us_id → list], edge: list}
- `verification_map`: dict[us_id → list[task_id]]
- `open_questions`: list[str] (surface to user)
- `deferred`: list[str] (separate section)
