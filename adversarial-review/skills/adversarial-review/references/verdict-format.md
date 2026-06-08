## Verdict / Report Format

The orchestrator emits ONE synthesized advisory report after the refute pass (SOP Step 5). Advisory — it does not auto-block.

---

```
## Adversarial Review — {artifact}

**Intent reviewed against:** {one-sentence intent}
**Grounding:** {files used}
**Lenses:** {Skeptic / Architect / Minimalist / Security} · cross-model: {yes/no}

### Confirmed findings
| # | class | severity | finding | span (location) | violates / underspecifies | failure scenario |
|---|-------|----------|---------|-----------------|---------------------------|------------------|
| 1 | DEFECT | HIGH | … | "…" (KD8 / line 109) | MR1 / NFR1 | … |
| 2 | SCOPE | MEDIUM | … | "…" (§Scope) | scope silent on whether X is in/deferred | … |

class ∈ {DEFECT (breaks a stated claim), SCOPE (underspecified + scope doesn't resolve), DEFERRED (scope explicitly defers → LOW/note-only)}.

### Reliability ratings (rate even where COVERED)
| area / requirement | reliability | reasoning |
|--------------------|-------------|-----------|
| MR7 join tracking | MEDIUM | covered but fragile because … |

### Strategy recommendations (advisory — take or leave)
- <intent inconsistency, or a simpler/more durable approach for this purpose or a future need — caller decides>

### Scope clarity
- <is the artifact's in/out/deferred scope crisp enough to judge against? fuzzy scope is itself the reason SCOPE-class findings exist>

### Rejected as false-positive
- <finding> — dropped: <cited span doesn't support it / requirement not real / refuted by grounding>

### Graduate candidates (→ /flag-imp to codify as a /verify rule)
- <finding class likely to recur across artifacts>

### Bottom line
- Most dangerous gap: <one>
- Least reliable "covered" claim: <one>
- Recommended action: <advisory — lead decides; high-severity ship-past is recorded with a reason>
```

---

Rules:
- **Confirmed** = survived the refute pass (cited span verified, requirement real).
- **Reliability** is separate from findings: an area can have zero open findings yet rate MEDIUM/LOW because it is fragile, ambiguous, or human-discipline-dependent.
- **Rejected** is kept on purpose — it builds the false-positive catalog that tunes future runs (Reflexion-style memory).
- **Graduate candidates** close the loop to checklist `/verify`: a recurring adversarial finding becomes a cheap deterministic rule.
