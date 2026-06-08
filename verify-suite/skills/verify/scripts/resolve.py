#!/usr/bin/env python3
"""resolve.py — Config resolution: type(s) → rule list JSON.

Reads base artifact-config.yaml, merges project overlay if present,
resolves rule paths from rules/general/ + rules/overlays/{domain}/,
extracts rule frontmatter metadata, returns merged rule list as JSON.

Usage:
    python3 resolve.py <type>               # single type
    python3 resolve.py <type1,type2>        # multi-type (comma-separated)
    python3 resolve.py <type> --spec-folder <path>  # with project overlay
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import yaml


SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "artifact-config.yaml"
RULES_DIR = SKILL_DIR / "rules"


def load_yaml(path: Path) -> dict:
    """Load a YAML file, raising on missing or malformed."""
    if not path.exists():
        print(json.dumps({"error": f"Config not found: {path}"}))
        sys.exit(1)
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(json.dumps({"error": f"Config parse error: {path}: {e}"}))
        sys.exit(1)


def parse_rule_frontmatter(rule_path: Path) -> dict | None:
    """Extract YAML frontmatter from a rule markdown file."""
    if not rule_path.exists():
        return None
    text = rule_path.read_text()
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        return yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None


def resolve_rule_path(rule_id: str, domain: str | None) -> Path:
    """Return rule path, checking structural/ first then general/."""
    structural_path = RULES_DIR / "structural" / f"{rule_id}.md"
    if structural_path.exists():
        return structural_path
    return RULES_DIR / "general" / f"{rule_id}.md"


def get_overlay_path(rule_id: str, domain: str | None) -> Path | None:
    """Return domain overlay path if domain is set."""
    if not domain:
        return None
    overlay = RULES_DIR / "overlays" / domain / f"{rule_id}.md"
    return overlay if overlay.exists() else None


def merge_project_overlay(base_config: dict, spec_folder: str | None) -> dict:
    """Merge project-level .verify-overlay.yaml into base config."""
    if not spec_folder:
        return base_config

    overlay_path = Path(spec_folder) / ".verify-overlay.yaml"
    if not overlay_path.exists():
        return base_config

    try:
        with open(overlay_path) as f:
            overlay = yaml.safe_load(f) or {}
    except yaml.YAMLError:
        # Malformed overlay — warn but continue with base
        return base_config

    merged = dict(base_config)
    for artifact_type, overrides in overlay.items():
        if artifact_type not in merged:
            continue
        type_config = dict(merged[artifact_type])

        # Apply domain override
        if "domain" in overrides:
            type_config["domain"] = overrides["domain"]

        # Apply add/skip per phase
        for phase in ("structural", "quality"):
            if phase not in overrides:
                continue
            phase_rules = list(type_config.get(phase, []))
            phase_overrides = overrides[phase]

            if isinstance(phase_overrides, dict):
                # Add rules (deduplicated)
                for rule_id in phase_overrides.get("add", []):
                    if rule_id not in phase_rules:
                        phase_rules.append(rule_id)
                # Skip rules
                skip_entries = phase_overrides.get("skip", [])
                skip_ids = set()
                for entry in skip_entries:
                    if isinstance(entry, dict):
                        skip_ids.add(entry.get("rule", ""))
                    else:
                        skip_ids.add(str(entry))
                phase_rules = [r for r in phase_rules if r not in skip_ids]

            type_config[phase] = phase_rules

        merged[artifact_type] = type_config

    return merged


def resolve_rules(types: list[str], config: dict) -> list[dict]:
    """Resolve rule list for given type(s). Returns list of rule metadata dicts."""
    seen_ids = set()
    rules = []

    for artifact_type in types:
        if artifact_type not in config:
            print(json.dumps({"error": f"Unknown artifact type: '{artifact_type}'. Available: {list(config.keys())}"}))
            sys.exit(1)

        type_config = config[artifact_type]
        domain = type_config.get("domain")

        for stage in ("structural", "quality"):
            for rule_id in type_config.get(stage, []):
                if rule_id in seen_ids:
                    continue
                seen_ids.add(rule_id)

                rule_path = resolve_rule_path(rule_id, domain)
                overlay_path = get_overlay_path(rule_id, domain)

                # Extract frontmatter
                meta = parse_rule_frontmatter(rule_path)
                if meta is None:
                    # Rule file missing or unparseable — still include for error reporting
                    rules.append({
                        "id": rule_id,
                        "path": str(rule_path),
                        "overlay_path": str(overlay_path) if overlay_path else None,
                        "model_hint": "opus",  # default on error
                        "stage": stage,
                        "severity": "blocking",
                        "inputs": ["artifact"],
                        "error": f"Rule file missing or unparseable: {rule_path}",
                    })
                    continue

                rules.append({
                    "id": meta.get("id", rule_id),
                    "path": str(rule_path),
                    "overlay_path": str(overlay_path) if overlay_path else None,
                    "name": meta.get("name", rule_id),
                    "description": meta.get("description", ""),
                    "model_hint": meta.get("model_hint", "opus"),
                    "stage": meta.get("stage", stage),
                    "severity": meta.get("severity", "blocking"),
                    "inputs": meta.get("inputs", ["artifact"]),
                })

    return rules


def resolve_rules_by_id(rule_ids: list[str]) -> list[dict]:
    """Resolve rules by explicit IDs, bypassing artifact-config.yaml."""
    rules = []
    for rule_id in rule_ids:
        # Search structural/ first, then general/
        structural_path = RULES_DIR / "structural" / f"{rule_id}.md"
        general_path = RULES_DIR / "general" / f"{rule_id}.md"

        if structural_path.exists():
            rule_path = structural_path
        elif general_path.exists():
            rule_path = general_path
        else:
            rules.append({
                "id": rule_id,
                "error": "rule not found",
            })
            continue

        meta = parse_rule_frontmatter(rule_path)
        if meta is None:
            rules.append({
                "id": rule_id,
                "path": str(rule_path),
                "stage": "quality",
                "error": f"Rule file missing or unparseable: {rule_path}",
            })
            continue

        rules.append({
            "id": meta.get("id", rule_id),
            "path": str(rule_path),
            "overlay_path": None,
            "name": meta.get("name", rule_id),
            "description": meta.get("description", ""),
            "model_hint": meta.get("model_hint", "opus"),
            "stage": "quality",
            "severity": meta.get("severity", "blocking"),
            "inputs": meta.get("inputs", ["artifact"]),
        })

    return rules


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: resolve.py <type[,type2]> [--spec-folder <path>] | --rules <id1,id2>"}))
        sys.exit(1)

    # Parse --rules argument
    rules_arg = None
    if "--rules" in sys.argv:
        idx = sys.argv.index("--rules")
        if idx + 1 < len(sys.argv):
            rules_arg = sys.argv[idx + 1]

    # Parse type: positional first arg or --type flag
    type_arg = None
    if "--type" in sys.argv:
        idx = sys.argv.index("--type")
        if idx + 1 < len(sys.argv):
            type_arg = sys.argv[idx + 1]
    elif len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        type_arg = sys.argv[1]

    # Mutual exclusion check
    if rules_arg and type_arg:
        print(json.dumps({"error": "--rules and --type are mutually exclusive"}))
        sys.exit(1)

    # --rules mode: bypass artifact-config entirely
    if rules_arg:
        rule_ids = [r.strip() for r in rules_arg.split(",")]
        rules = resolve_rules_by_id(rule_ids)
        print(json.dumps(rules, indent=2))
        return

    # --type mode (existing behavior)
    if not type_arg:
        print(json.dumps({"error": "Usage: resolve.py <type[,type2]> [--spec-folder <path>] | --rules <id1,id2>"}))
        sys.exit(1)

    types = [t.strip() for t in type_arg.split(",")]

    spec_folder = None
    if "--spec-folder" in sys.argv:
        idx = sys.argv.index("--spec-folder")
        if idx + 1 < len(sys.argv):
            spec_folder = sys.argv[idx + 1]

    config = load_yaml(CONFIG_PATH)
    config = merge_project_overlay(config, spec_folder)
    rules = resolve_rules(types, config)

    print(json.dumps(rules, indent=2))


if __name__ == "__main__":
    main()
