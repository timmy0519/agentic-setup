#!/usr/bin/env python3
"""compile.py — Deterministic compiler: manifest → rule files + artifact-config.yaml.

Reads a verify-compiler manifest (YAML) and generates:
  1. Rule files (markdown + YAML frontmatter) in rules/general/ and rules/overlays/
  2. artifact-config.yaml mapping artifact types to rule IDs per stage

Usage:
    python3 compile.py --manifest <path> --dry-run     # print summary, write nothing
    python3 compile.py --manifest <path> --apply        # write files (skip existing)
    python3 compile.py --manifest <path> --apply --force  # overwrite existing rule files
    cat manifest.yaml | python3 compile.py --apply      # read from stdin
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


SKILL_DIR = Path(__file__).resolve().parent.parent
RULES_DIR = SKILL_DIR / "rules"
GENERAL_DIR = RULES_DIR / "general"
CONFIG_PATH = SKILL_DIR / "artifact-config.yaml"
DATAPOINTS_PATH = SKILL_DIR / ".verify-datapoints.yaml"


def load_manifest(manifest_path: str | None) -> dict:
    """Load manifest from path or stdin."""
    if manifest_path:
        p = Path(manifest_path)
        if not p.exists():
            print(f"Error: manifest not found: {p}", file=sys.stderr)
            sys.exit(1)
        with open(p) as f:
            return yaml.safe_load(f)
    else:
        return yaml.safe_load(sys.stdin)


def rule_to_markdown(rule: dict) -> str:
    """Convert a manifest rule entry to markdown with YAML frontmatter."""
    # Build frontmatter
    fm: dict[str, Any] = {
        "name": rule["name"],
        "id": rule["id"],
        "description": rule["evaluation_summary"],
        "stage": rule["stage"],
        "severity": rule["severity"],
        "model_hint": rule["model_hint"],
        "inputs": rule["inputs"],
    }

    # Serialize frontmatter — force inputs to inline list format
    # Use flow_style for inputs by removing it from the dict and appending manually
    fm_no_inputs = {k: v for k, v in fm.items() if k != "inputs"}
    fm_yaml = yaml.dump(fm_no_inputs, default_flow_style=False, sort_keys=False, allow_unicode=True).rstrip()
    inputs_line = f"inputs: [{', '.join(rule['inputs'])}]"
    fm_yaml = fm_yaml + "\n" + inputs_line

    # Build body
    body_parts = ["## Evaluation prompt", ""]
    prompt = rule["evaluation_prompt"].strip()
    body_parts.append(prompt)

    return f"---\n{fm_yaml}\n---\n\n" + "\n".join(body_parts) + "\n"


def principle_to_markdown(principle: dict) -> str:
    """Convert a principle manifest entry to markdown with YAML frontmatter."""
    fm: dict[str, Any] = {
        "name": principle["name"],
        "id": principle["id"],
        "description": principle["statement"],
        "stage": principle["stage"],
        "severity": principle["severity"],
        "model_hint": principle["model_hint"],
        "inputs": principle["inputs"],
        "constituent_checks": [c["id"] for c in principle["constituent_checks"]],
    }

    # Serialize frontmatter — inline lists for inputs and constituent_checks
    fm_scalar = {k: v for k, v in fm.items() if k not in ("inputs", "constituent_checks")}
    fm_yaml = yaml.dump(fm_scalar, default_flow_style=False, sort_keys=False, allow_unicode=True).rstrip()
    fm_yaml += f"\ninputs: [{', '.join(principle['inputs'])}]"
    checks_list = ", ".join(c["id"] for c in principle["constituent_checks"])
    fm_yaml += f"\nconstituent_checks: [{checks_list}]"

    # Build body — principle statement leads, checks as illustrations
    body_parts = ["## Evaluation prompt", ""]
    body_parts.append(principle["statement"])
    body_parts.append("")
    body_parts.append("**Illustrations of this principle** (non-exhaustive — apply the principle even")
    body_parts.append("to cases not listed here):")
    body_parts.append("")
    for check in principle["constituent_checks"]:
        body_parts.append(f"- **{check['id']}**: {check['what']}")
    body_parts.append("")
    body_parts.append("For each violation found:")
    body_parts.append("1. Name which illustration (or novel case) it falls under")
    body_parts.append("2. Quote the exact text and line number")
    body_parts.append("3. State why it violates the principle")
    body_parts.append("4. Suggest a concrete fix")
    body_parts.append("")
    body_parts.append("If no violations are found, state PASS.")
    body_parts.append("If one or more violations are found, state FAIL with all occurrences listed.")

    # Boundary examples
    boundary = principle.get("boundary_examples", {})
    if boundary:
        body_parts.append("")
        body_parts.append("## Boundary examples")
        body_parts.append("")
        if "pass" in boundary:
            body_parts.append(f"**PASS:** {boundary['pass']}")
        body_parts.append("")
        if "fail" in boundary:
            body_parts.append(f"**FAIL:** {boundary['fail']}")

    return f"---\n{fm_yaml}\n---\n\n" + "\n".join(body_parts) + "\n"


def standalone_to_markdown(rule: dict) -> str:
    """Convert a standalone rule from principle manifest to markdown."""
    fm: dict[str, Any] = {
        "name": rule["name"],
        "id": rule["id"],
        "description": rule["description"],
        "stage": rule["stage"],
        "severity": rule["severity"],
        "model_hint": rule["model_hint"],
        "inputs": rule["inputs"],
    }

    fm_scalar = {k: v for k, v in fm.items() if k != "inputs"}
    fm_yaml = yaml.dump(fm_scalar, default_flow_style=False, sort_keys=False, allow_unicode=True).rstrip()
    fm_yaml += f"\ninputs: [{', '.join(rule['inputs'])}]"

    body_parts = ["## Evaluation prompt", ""]
    body_parts.append(rule["evaluation_prompt"].strip())

    boundary = rule.get("boundary_examples", {})
    if boundary:
        body_parts.append("")
        body_parts.append("## Boundary examples")
        body_parts.append("")
        if "pass" in boundary:
            body_parts.append(f"**PASS:** {boundary['pass']}")
        body_parts.append("")
        if "fail" in boundary:
            body_parts.append(f"**FAIL:** {boundary['fail']}")

    return f"---\n{fm_yaml}\n---\n\n" + "\n".join(body_parts) + "\n"


def build_principle_config(manifest: dict) -> dict:
    """Build artifact-config.yaml from a principle-level manifest."""
    type_stages: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"structural": [], "quality": []})

    # Process principles
    for p in manifest.get("principles", []):
        stage = p["stage"]
        rule_id = p["id"]
        for at in p.get("artifact_types", []):
            if rule_id not in type_stages[at][stage]:
                type_stages[at][stage].append(rule_id)

    # Process standalone rules
    for r in manifest.get("standalone", []):
        stage = r["stage"]
        rule_id = r["id"]
        for at in r.get("artifact_types", []):
            if rule_id not in type_stages[at][stage]:
                type_stages[at][stage].append(rule_id)

    # Build output dict preserving order: requirements, design, task
    config: dict[str, Any] = {}
    for at in ["requirements", "design", "task"]:
        if at not in type_stages:
            continue
        entry: dict[str, Any] = {}
        # Preserve agentic domain for design
        if at == "design":
            entry["domain"] = "agentic"
        entry["structural"] = type_stages[at]["structural"]
        entry["quality"] = type_stages[at]["quality"]
        config[at] = entry

    return config


def build_config(manifest: dict) -> dict:
    """Build artifact-config.yaml content from manifest rules."""
    # Collect rule IDs per artifact_type per stage
    type_stages: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"structural": [], "quality": []})

    # Track which types need domain overlay
    type_domains: dict[str, str | None] = {}

    for rule in manifest["rules"]:
        artifact_types = rule.get("artifact_type", [])
        if isinstance(artifact_types, str):
            artifact_types = [artifact_types]

        stage = rule["stage"]
        rule_id = rule["id"]
        domain = rule.get("domain", "general")

        for at in artifact_types:
            if rule_id not in type_stages[at][stage]:
                type_stages[at][stage].append(rule_id)
            if domain != "general" and at not in type_domains:
                type_domains[at] = domain

    # Add existing hand-tuned rules that aren't in the manifest
    existing_extras = {
        "requirements": {
            "structural": ["no-vague-language"],
            "quality": ["subtraction-test", "requirements-coverage"],
        },
        "design": {
            "structural": [],  # no-vague-language already in manifest for design
            "quality": ["subtraction-test", "requirements-coverage"],
        },
        "task": {
            "structural": [],
            "quality": ["subtraction-test"],
        },
    }

    for at, stages in existing_extras.items():
        for stage, rule_ids in stages.items():
            for rid in rule_ids:
                if rid not in type_stages[at][stage]:
                    type_stages[at][stage].append(rid)

    # Build output dict preserving order: requirements, design, task
    config: dict[str, Any] = {}
    for at in ["requirements", "design", "task"]:
        if at not in type_stages:
            continue
        entry: dict[str, Any] = {}
        if at in type_domains and type_domains[at]:
            entry["domain"] = type_domains[at]
        entry["structural"] = type_stages[at]["structural"]
        entry["quality"] = type_stages[at]["quality"]
        config[at] = entry

    # Ensure design has agentic domain (for the existing agentic overlay)
    if "design" in config and "domain" not in config["design"]:
        config["design"] = {"domain": "agentic", **config["design"]}

    return config


def dry_run_principles(manifest: dict):
    """Print principle manifest summary without writing files."""
    principles = manifest.get("principles", [])
    standalone = manifest.get("standalone", [])

    print("=== verify-compiler dry-run (principle mode) ===\n")

    # Principles
    print(f"Principles: {len(principles)}")
    for p in principles:
        checks = [c["id"] for c in p.get("constituent_checks", [])]
        print(f"  [{p['stage'][:5]}] {p['id']} ({len(checks)} checks) → {p['severity']} ({p['model_hint']})")
        for c in checks:
            print(f"         ↳ {c}")

    # Standalone
    print(f"\nStandalone rules: {len(standalone)}")
    for r in standalone:
        print(f"  [{r['stage'][:5]}] {r['id']} → {r['severity']} ({r['model_hint']})")

    # Total
    total = len(principles) + len(standalone)
    total_checks = sum(len(p.get("constituent_checks", [])) for p in principles)
    print(f"\nTotal rules: {total} ({len(principles)} principles absorbing {total_checks} checks + {len(standalone)} standalone)")

    # By artifact type
    by_type: dict[str, int] = defaultdict(int)
    for p in principles:
        for at in p.get("artifact_types", []):
            by_type[at] += 1
    for r in standalone:
        for at in r.get("artifact_types", []):
            by_type[at] += 1
    print("\nBy artifact type:")
    for at in sorted(by_type):
        print(f"  {at}: {by_type[at]}")

    # Config preview
    config = build_principle_config(manifest)
    print("\nConfig preview:")
    for at, cfg in config.items():
        structural = cfg.get("structural", [])
        quality = cfg.get("quality", [])
        print(f"  {at}: {len(structural)} structural, {len(quality)} quality")

    print("\nUse --apply --principles to write files.")


def apply_principles(manifest: dict, force: bool = False):
    """Write principle-level rule files and artifact-config.yaml."""
    principles = manifest.get("principles", [])
    standalone = manifest.get("standalone", [])

    created = 0
    skipped = 0
    overwritten = 0

    GENERAL_DIR.mkdir(parents=True, exist_ok=True)

    # Write principle rule files
    for p in principles:
        out_path = GENERAL_DIR / f"{p['id']}.md"

        if out_path.exists() and not force:
            print(f"  SKIP (exists):    {out_path.relative_to(SKILL_DIR)}")
            skipped += 1
            continue

        content = principle_to_markdown(p)
        existed = out_path.exists()
        out_path.write_text(content)

        if existed and force:
            print(f"  OVERWRITE:        {out_path.relative_to(SKILL_DIR)}")
            overwritten += 1
        else:
            print(f"  CREATE:           {out_path.relative_to(SKILL_DIR)}")
            created += 1

    # Write standalone rule files
    for r in standalone:
        out_path = GENERAL_DIR / f"{r['id']}.md"

        if out_path.exists() and not force:
            print(f"  SKIP (exists):    {out_path.relative_to(SKILL_DIR)}")
            skipped += 1
            continue

        content = standalone_to_markdown(r)
        existed = out_path.exists()
        out_path.write_text(content)

        if existed and force:
            print(f"  OVERWRITE:        {out_path.relative_to(SKILL_DIR)}")
            overwritten += 1
        else:
            print(f"  CREATE:           {out_path.relative_to(SKILL_DIR)}")
            created += 1

    # Generate artifact-config.yaml
    config = build_principle_config(manifest)
    config_content = yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)
    CONFIG_PATH.write_text(config_content)
    print(f"\n  WRITE:            artifact-config.yaml")

    # Summary
    total = len(principles) + len(standalone)
    print(f"\nDone: {created} created, {skipped} skipped, {overwritten} overwritten (of {total} total)")
    print(f"Config written to: {CONFIG_PATH}")


def dry_run(manifest: dict):
    """Print manifest summary without writing files."""
    rules = manifest.get("rules", [])
    summary = manifest.get("summary", {})

    print("=== verify-compiler dry-run ===\n")

    # Source SOPs
    print("Source SOPs:")
    for sop in manifest.get("source_sops", []):
        print(f"  {sop['path']}  ({sop['checks_extracted']} checks)")

    # Dedup decisions
    print(f"\nDedup decisions: {len(manifest.get('dedup_decisions', []))}")
    for dd in manifest.get("dedup_decisions", []):
        print(f"  {dd['decision'].upper()}: {dd.get('merged_id', dd['candidates'])}")
        print(f"    {dd['rationale'][:80]}...")

    # Summary counts
    print(f"\nTotal checks extracted: {summary.get('total_checks_extracted', len(rules))}")
    print(f"Unique rules after dedup: {summary.get('unique_rules_after_dedup', len(rules))}")

    # By stage
    structural = [r for r in rules if r["stage"] == "structural"]
    quality = [r for r in rules if r["stage"] == "quality"]
    print(f"  structural: {len(structural)}")
    print(f"  quality:    {len(quality)}")

    # By artifact type
    by_type: dict[str, int] = defaultdict(int)
    for r in rules:
        ats = r.get("artifact_type", [])
        if isinstance(ats, str):
            ats = [ats]
        for at in ats:
            by_type[at] += 1
    print("\nBy artifact type:")
    for at in sorted(by_type):
        print(f"  {at}: {by_type[at]}")

    # Existing rules that will be preserved
    preserved = summary.get("existing_rules_preserved", [])
    if preserved:
        print(f"\nExisting rules preserved (not overwritten): {len(preserved)}")
        for p in preserved:
            print(f"  {p}")

    # List all rule IDs
    print(f"\nAll rule IDs ({len(rules)}):")
    for r in rules:
        marker = "*" if r["id"] in [p.split("/")[-1] for p in preserved] else " "
        print(f"  {marker} [{r['stage'][:5]}] {r['id']} → {r['severity']} ({r['model_hint']})")

    print("\nUse --apply to write files.")


def apply(manifest: dict, force: bool = False):
    """Write rule files and artifact-config.yaml."""
    rules = manifest.get("rules", [])
    preserved = set()
    for p in manifest.get("summary", {}).get("existing_rules_preserved", []):
        preserved.add(p.split("/")[-1])  # normalize overlay paths

    created = 0
    skipped = 0
    overwritten = 0

    # Ensure directories exist
    GENERAL_DIR.mkdir(parents=True, exist_ok=True)

    for rule in rules:
        rule_id = rule["id"]
        domain = rule.get("domain", "general")

        # Determine output path
        if domain != "general":
            out_dir = RULES_DIR / "overlays" / domain
        else:
            out_dir = GENERAL_DIR

        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{rule_id}.md"

        # Check if this is an existing preserved rule
        if rule_id in preserved and out_path.exists():
            print(f"  SKIP (preserved): {out_path.relative_to(SKILL_DIR)}")
            skipped += 1
            continue

        # Check if file exists
        if out_path.exists() and not force:
            print(f"  SKIP (exists):    {out_path.relative_to(SKILL_DIR)}")
            skipped += 1
            continue

        # Write rule file
        content = rule_to_markdown(rule)
        out_path.write_text(content)

        if out_path.exists() and force:
            print(f"  OVERWRITE:        {out_path.relative_to(SKILL_DIR)}")
            overwritten += 1
        else:
            print(f"  CREATE:           {out_path.relative_to(SKILL_DIR)}")
            created += 1

    # Generate artifact-config.yaml
    config = build_config(manifest)
    config_content = yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)
    CONFIG_PATH.write_text(config_content)
    print(f"\n  WRITE:            artifact-config.yaml")

    # Summary
    print(f"\nDone: {created} created, {skipped} skipped, {overwritten} overwritten")
    print(f"Config written to: {CONFIG_PATH}")


def load_datapoints() -> list[dict]:
    """Load datapoints from .verify-datapoints.yaml."""
    if not DATAPOINTS_PATH.exists():
        print(f"Error: datapoints file not found: {DATAPOINTS_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(DATAPOINTS_PATH) as f:
        data = yaml.safe_load(f)
    return data.get("datapoints", []) or []


def load_artifact_config() -> dict:
    """Load artifact-config.yaml and return all rule_ids."""
    if not CONFIG_PATH.exists():
        print(f"Error: artifact-config not found: {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def evolve():
    """Analyze datapoints and output evolution recommendations as YAML."""
    datapoints = load_datapoints()
    if not datapoints:
        print("No datapoints recorded yet. Nothing to evolve.")
        return

    # Group by observation_type
    by_type: dict[str, list[dict]] = defaultdict(list)
    for dp in datapoints:
        by_type[dp.get("observation_type", "unknown")].append(dp)

    actions: list[dict[str, Any]] = []

    # False positives: group by rule_id, threshold >= 3
    fps = by_type.get("false_positive", [])
    if fps:
        by_rule: dict[str, list[dict]] = defaultdict(list)
        for dp in fps:
            by_rule[dp["rule_id"]].append(dp)
        for rule_id, entries in by_rule.items():
            if len(entries) >= 3:
                examples = []
                for e in entries:
                    corr = e.get("correction", {})
                    if corr and corr.get("what_actually_happened"):
                        examples.append(corr["what_actually_happened"])
                actions.append({
                    "action": "CALIBRATE",
                    "rule_id": rule_id,
                    "count": len(entries),
                    "recommendation": f"Tighten boundary, add these as PASS examples",
                    "examples": examples,
                })

    # False negatives: group by evidence_category, threshold >= 3
    fns = by_type.get("false_negative", [])
    if fns:
        by_category: dict[str, list[dict]] = defaultdict(list)
        for dp in fns:
            corr = dp.get("correction", {})
            cat = corr.get("evidence_category", "uncategorized") if corr else "uncategorized"
            by_category[cat].append(dp)
        for category, entries in by_category.items():
            if len(entries) >= 3:
                principles = []
                for e in entries:
                    corr = e.get("correction", {})
                    if corr and corr.get("principle_violated"):
                        principles.append(corr["principle_violated"])
                actions.append({
                    "action": "GAP",
                    "evidence_category": category,
                    "count": len(entries),
                    "recommendation": f"New rule needed for '{category}'",
                    "grounded_in": list(set(principles)),
                })

    # Inconsistencies: group by rule_id, threshold >= 2
    incons = by_type.get("inconsistency", [])
    if incons:
        by_rule_i: dict[str, list[dict]] = defaultdict(list)
        for dp in incons:
            by_rule_i[dp["rule_id"]].append(dp)
        for rule_id, entries in by_rule_i.items():
            if len(entries) >= 2:
                actions.append({
                    "action": "FREEZE",
                    "rule_id": rule_id,
                    "count": len(entries),
                    "recommendation": "Rewrite prompt, resolve ambiguity",
                })

    if not actions:
        print("No evolution triggers met thresholds yet.")
        print(f"  false_positive entries: {len(fps)} (need 3+ per rule_id)")
        print(f"  false_negative entries: {len(fns)} (need 3+ per evidence_category)")
        print(f"  inconsistency entries:  {len(incons)} (need 2+ per rule_id)")
        return

    # Output as YAML manifest
    output = {"evolution_recommendations": actions}
    print(yaml.dump(output, default_flow_style=False, sort_keys=False, allow_unicode=True))


def check_dormancy():
    """Check for dormant rules — rules with 30+ verdicts and 0 FAIL/CONSIDER."""
    datapoints = load_datapoints()
    config = load_artifact_config()

    # Collect all rule_ids from artifact-config.yaml
    all_rule_ids: set[str] = set()
    for artifact_type, cfg in config.items():
        if isinstance(cfg, dict):
            for stage_key in ("structural", "quality"):
                for rid in cfg.get(stage_key, []):
                    all_rule_ids.add(rid)

    # Count verdicts per rule_id
    verdict_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "fail_or_consider": 0})
    for dp in datapoints:
        rid = dp.get("rule_id", "")
        if rid:
            verdict_counts[rid]["total"] += 1
            if dp.get("verdict") in ("FAIL", "CONSIDER"):
                verdict_counts[rid]["fail_or_consider"] += 1

    dormant: list[dict[str, Any]] = []
    for rid in sorted(all_rule_ids):
        counts = verdict_counts.get(rid, {"total": 0, "fail_or_consider": 0})
        if counts["total"] >= 30 and counts["fail_or_consider"] == 0:
            dormant.append({
                "action": "DORMANT",
                "rule_id": rid,
                "total_verdicts": counts["total"],
                "recommendation": "Investigate — 30+ verdicts, 0 FAIL/CONSIDER",
            })

    if not dormant:
        # Show summary anyway
        rules_with_data = {rid for rid in all_rule_ids if verdict_counts.get(rid, {}).get("total", 0) > 0}
        print(f"No dormant rules detected.")
        print(f"  Rules in config: {len(all_rule_ids)}")
        print(f"  Rules with verdict data: {len(rules_with_data)}")
        print(f"  Total datapoints: {len(datapoints)}")
        return

    output = {"dormancy_report": dormant}
    print(yaml.dump(output, default_flow_style=False, sort_keys=False, allow_unicode=True))


def main():
    parser = argparse.ArgumentParser(description="verify-compiler: manifest → rule files + config")
    parser.add_argument("--manifest", type=str, help="Path to manifest YAML (reads stdin if omitted)")
    parser.add_argument("--dry-run", action="store_true", help="Print summary, write nothing")
    parser.add_argument("--apply", action="store_true", help="Write rule files and config")
    parser.add_argument("--force", action="store_true", help="Overwrite existing rule files")
    parser.add_argument("--principles", action="store_true", help="Use principle-level manifest format (principles + standalone)")
    parser.add_argument("--evolve", action="store_true", help="Analyze datapoints and output evolution recommendations")
    parser.add_argument("--check-dormancy", action="store_true", help="Check for dormant rules with no FAIL/CONSIDER verdicts")

    args = parser.parse_args()

    if args.evolve:
        evolve()
        return

    if args.check_dormancy:
        check_dormancy()
        return

    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run, --apply, --evolve, or --check-dormancy")

    manifest = load_manifest(args.manifest)

    if args.principles:
        if args.dry_run:
            dry_run_principles(manifest)
        elif args.apply:
            apply_principles(manifest, force=args.force)
    else:
        if args.dry_run:
            dry_run(manifest)
        elif args.apply:
            apply(manifest, force=args.force)


if __name__ == "__main__":
    main()
