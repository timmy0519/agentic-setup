---
name: rule-meta-complete
applies_to:
  doctype: [verify-rule]
  stage: [write, verify]
severity: blocking
---

## Evaluation

Every rule file in `${CLAUDE_PLUGIN_ROOT}/skills/verify/rules/**/*.md` MUST declare YAML frontmatter with:

- `name` — kebab-case slug matching the rule identifier
- `applies_to.doctype` — list of doctype strings (or `"*"` for universal), e.g. `[spec-req, research-note]`
- `applies_to.stage` — list of stage strings (or `"*"`), e.g. `[write, verify]` or `[verify]`
- `severity` — `blocking` or `advisory`

Missing frontmatter or missing required fields blocks write.

## Output

For each rule file checked, return:
- PASS / FAIL
- Missing fields if FAIL
- Suggested fix
