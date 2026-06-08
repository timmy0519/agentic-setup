#!/usr/bin/env python3
"""describe.py — Discoverability for the verify skill.

Modes:
    describe.py                    — list available artifact types with rule counts
    describe.py <type>             — list all rules for a type with descriptions
    describe.py --health-check     — check rule health staleness (90-day threshold)

Usage:
    python3 describe.py
    python3 describe.py design
    python3 describe.py --health-check
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "artifact-config.yaml"
RULES_DIR = SKILL_DIR / "rules"
HEALTH_PATH = SKILL_DIR / ".verify-rule-health.json"

STALENESS_DAYS = 90


def load_config() -> dict:
    """Load artifact config."""
    if not CONFIG_PATH.exists():
        print(f"Error: Config not found at {CONFIG_PATH}")
        sys.exit(1)
    try:
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"Error: Config parse error: {e}")
        sys.exit(1)


def parse_frontmatter(rule_path: Path) -> dict | None:
    """Extract YAML frontmatter from a rule file."""
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


def list_types(config: dict):
    """List available types with rule counts."""
    print("Available artifact types:\n")
    for type_name, type_config in config.items():
        structural = type_config.get("structural", [])
        quality = type_config.get("quality", [])
        domain = type_config.get("domain", "—")
        print(f"  {type_name}")
        print(f"    structural: {len(structural)} rules")
        print(f"    quality:    {len(quality)} rules")
        print(f"    domain:     {domain}")
        print()


def describe_type(config: dict, type_name: str):
    """Show all rules for a type with descriptions from frontmatter."""
    if type_name not in config:
        available = ", ".join(config.keys())
        print(f"Error: Type '{type_name}' not found. Available types: {available}")
        sys.exit(1)

    type_config = config[type_name]
    domain = type_config.get("domain")

    print(f"Rules for '{type_name}':\n")

    for stage in ("structural", "quality"):
        rules = type_config.get(stage, [])
        if not rules:
            continue
        print(f"  {stage.upper()}:")
        for rule_id in rules:
            structural_path = RULES_DIR / "structural" / f"{rule_id}.md"
            rule_path = structural_path if structural_path.exists() else RULES_DIR / "general" / f"{rule_id}.md"
            meta = parse_frontmatter(rule_path)
            if meta:
                desc = meta.get("description", "(no description)")
                severity = meta.get("severity", "?")
                model = meta.get("model_hint", "?")
                has_overlay = ""
                if domain:
                    overlay_path = RULES_DIR / "overlays" / domain / f"{rule_id}.md"
                    if overlay_path.exists():
                        has_overlay = " [+overlay]"
                print(f"    [{severity}] {rule_id} — {desc} (model: {model}){has_overlay}")
            else:
                print(f"    [?] {rule_id} — (rule file missing or unparseable)")
        print()


def health_check():
    """Check rule health staleness."""
    if not HEALTH_PATH.exists():
        print("STALE")
        print("No rule health file found")
        return

    try:
        with open(HEALTH_PATH) as f:
            health = json.load(f)
    except (json.JSONDecodeError, OSError):
        print("STALE")
        print("Rule health file corrupted")
        return

    last_review = health.get("last_review_date")
    if not last_review:
        print("STALE")
        print("No last_review_date in health file")
        return

    try:
        review_date = datetime.fromisoformat(last_review).replace(tzinfo=timezone.utc)
    except ValueError:
        print("STALE")
        print(f"Invalid date format: {last_review}")
        return

    now = datetime.now(timezone.utc)
    days_since = (now - review_date).days

    if days_since > STALENESS_DAYS:
        print("STALE")
        print(f"Last review: {last_review} ({days_since} days ago)")
    else:
        print("OK")
        print(f"Last review: {last_review} ({days_since} days ago)")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--health-check":
        health_check()
        return

    config = load_config()

    if len(sys.argv) < 2:
        list_types(config)
    else:
        describe_type(config, sys.argv[1])


if __name__ == "__main__":
    main()
