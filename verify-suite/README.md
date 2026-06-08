# verify-suite

The verification plugin for the agentic-setup ecosystem. Bundles the verify engine, its durable rule-pack (the AC library), the `verify-*` review-skill family, and the `artifact-flow` task router.

## Bundled skills

| Skill | Role |
|-------|------|
| `verify` | Verification engine + rule-pack. `skills/verify/rules/` holds the durable acceptance-criteria library (`general/`, `structural/`, `overlays/`) plus selector scripts under `skills/verify/scripts/`. |
| `verify-spec` | Orchestrator — runs verify-requirements + verify-design + verify-task, consolidated PASS/FAIL. |
| `verify-requirements` | Leaf — structural + completeness checks on `requirements.md`. |
| `verify-design` | Leaf — structural checklist + requirement coverage on `design.md`. |
| `verify-task` | Leaf — checkbox/structure checks + design coverage on `task.md`. |
| `verify-note` | Orchestrator — runs verify-format + verify-content on a research note. |
| `verify-format` | Leaf — research-note format checklist. |
| `verify-content` | Leaf — depth/intuition review; expands thin sections. |
| `artifact-flow` | Task-class router → minimum-viable artifact set → per-artifact write/verify loop. Depends on the review skills above, which is why it ships here. |

## Dependencies

- **`adversarial-review`** (declared in `plugin.json`): the verify engine's Mode-2 / Step 9.5 invokes the adversarial-review skill as an advisory soft-gate. Install that plugin alongside this one.

## Hook

`hooks/hooks.json` registers a `PreToolUse` hook on `Write|Edit` that runs `hooks/pretooluse_write.sh`, which injects the applicable rule manifest before a file write.

The hook is **self-contained**: the selector scripts (`doctype_from_path.py`, `select_rules.py`) are bundled under `lib/`, and the script resolves them — plus the rules text — via `${CLAUDE_PLUGIN_ROOT}` (`${CLAUDE_PLUGIN_ROOT}/lib`, `${CLAUDE_PLUGIN_ROOT}/skills/verify/rules/`). `select_rules.py` locates the rule-pack `__file__`-relative (`parents[1]/skills/verify/rules`), which the plugin layout replicates, so no code edit was needed. Verified end-to-end: a simulated `Write` to a `requirements.md` resolves doctype `spec-req` and injects the matching rule manifest. The live `.claude/lib` original is untouched.

## Layout

```
verify-suite/
  .claude-plugin/plugin.json   # name, version, dependencies: [adversarial-review]
  skills/                      # verify engine + rule-pack + verify-* family + artifact-flow
  lib/                         # doctype_from_path.py, select_rules.py (bundled selector scripts)
  hooks/                       # hooks.json + pretooluse_write.sh (rewired to ${CLAUDE_PLUGIN_ROOT})
```
