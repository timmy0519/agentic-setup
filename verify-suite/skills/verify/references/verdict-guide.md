## Verdict Guide for Rule Subagents

Read this before evaluating. It defines what each verdict means and how to report your finding.

---

### Verdict definitions

| Verdict | Meaning | Use when |
|---------|---------|----------|
| **PASS** | Artifact satisfies this rule | No issues found |
| **FAIL** | Blocking violation — artifact cannot proceed | Missing required sections, structural defects, unmet requirements, broken contracts |
| **CONSIDER** | Advisory finding — worth attention, does not block | Style issues, potential over-engineering, improvement suggestions, minor gaps |
| **SKIP** | Rule cannot be evaluated | Missing input file, rule not applicable to this artifact type |

**Calibration guidance:**
- Do not default to FAIL when CONSIDER is more appropriate. FAIL means "must fix before proceeding." CONSIDER means "worth discussing."
- Do not inflate findings. If you find no issues, say PASS — don't manufacture concerns to appear thorough.
- If you're uncertain whether something is a violation, use CONSIDER with your reasoning. Let the caller decide.

### Severity (set by the rule, not by you)

Your rule's frontmatter specifies `severity: blocking` or `severity: advisory`. This is passed to you for context:
- **blocking** rules: violations produce FAIL
- **advisory** rules: violations produce CONSIDER (not FAIL)

If your rule is advisory, never return FAIL — return CONSIDER instead.

---

### How to report your finding

**Preferred — invoke the report script:**

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/verify/scripts/report.py \
  --rule-id {your rule id} \
  --verdict PASS|FAIL|CONSIDER|SKIP \
  --evidence "your evidence here" \
  --severity blocking|advisory \
  --confidence HIGH|MEDIUM|LOW
```

This produces structured JSON that the orchestrator can use directly.

**Fallback — if the script is unavailable**, use this labeled template:

```
RULE: {rule id}
VERDICT: PASS | FAIL | CONSIDER | SKIP
SEVERITY: blocking | advisory
EVIDENCE: {specific findings with line numbers and excerpts}
CONFIDENCE: HIGH | MEDIUM | LOW
```

**Confidence guide:**
- **HIGH** — clear-cut finding, strong evidence
- **MEDIUM** — judgment call, reasonable people could disagree
- **LOW** — uncertain, flagging for human review
