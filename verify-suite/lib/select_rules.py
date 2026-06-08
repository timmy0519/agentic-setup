#!/usr/bin/env python3
"""Select verify rules applicable to a doctype+stage. Returns compact manifest."""
import argparse
import os
import re
import sys
from pathlib import Path

RULES_ROOT = Path(__file__).resolve().parents[1] / "skills" / "verify" / "rules"

def parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from markdown content. Lightweight — no PyYAML dep.

    Supports: scalar values, inline [list] values, one-level nesting (applies_to),
    and YAML block-scalar markers (|, >) for multiline string values.
    """
    m = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return {}
    fm = {}
    block = m.group(1)
    lines = block.split("\n")
    i = 0
    current_key = None
    while i < len(lines):
        line = lines[i]
        line_stripped = line.rstrip()
        if not line_stripped or line_stripped.startswith("#"):
            i += 1
            continue
        # top-level key
        if not line.startswith(" ") and ":" in line_stripped:
            k, _, v = line_stripped.partition(":")
            k = k.strip()
            v = v.strip()
            if v in ("|", ">", "|-", ">-"):
                # block scalar — gather indented lines until next top-level key
                i += 1
                parts = []
                while i < len(lines):
                    ln = lines[i]
                    if ln.startswith(" ") or ln.strip() == "":
                        parts.append(ln.strip())
                        i += 1
                    else:
                        break
                fm[k] = " ".join(p for p in parts if p)
                current_key = None
                continue
            elif v:
                if v.startswith("[") and v.endswith("]"):
                    fm[k] = [x.strip().strip('"\'') for x in v[1:-1].split(",") if x.strip()]
                else:
                    fm[k] = v.strip('"\'')
                current_key = None
            else:
                fm[k] = {}
                current_key = k
        # nested under current_key (2-space indent)
        elif line.startswith("  ") and current_key and ":" in line_stripped:
            k, _, v = line_stripped.partition(":")
            k = k.strip()
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                fm[current_key][k] = [x.strip().strip('"\'') for x in v[1:-1].split(",") if x.strip()]
            else:
                fm[current_key][k] = v.strip('"\'')
        i += 1
    return fm

def load_rules() -> list:
    """Return list of dicts: {name, severity, applies_to, path, description}."""
    rules = []
    if not RULES_ROOT.exists():
        return rules
    for path in RULES_ROOT.rglob("*.md"):
        try:
            content = path.read_text()
            fm = parse_frontmatter(content)
            if not fm.get("name"):
                continue
            rules.append({
                "name": fm.get("name", path.stem),
                "severity": fm.get("severity", "advisory"),
                "applies_to": fm.get("applies_to", {}),
                "path": str(path),
                "description": (fm.get("description") or "").split("\n")[0][:140],
            })
        except Exception as e:
            # Lenient: skip parse failures, log to stderr
            print(f"select_rules: skip {path}: {e}", file=sys.stderr)
    return rules

def matches(rule: dict, doctype: str, stage: str) -> bool:
    """Check if rule applies to given doctype+stage. Lenient default: missing applies_to → universal."""
    at = rule.get("applies_to")
    if not at or not isinstance(at, dict):
        return True  # lenient — unannotated rules apply universally (with warning)
    dt = at.get("doctype")
    st = at.get("stage")
    # doctype check
    if dt and dt != "*":
        dt_list = dt if isinstance(dt, list) else [dt]
        if doctype not in dt_list and "*" not in dt_list:
            return False
    # stage check
    if st and st != "*":
        st_list = st if isinstance(st, list) else [st]
        if stage not in st_list and "*" not in st_list:
            return False
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--doctype", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--format", choices=["manifest", "json", "names"], default="manifest")
    args = parser.parse_args()

    rules = load_rules()
    filtered = [r for r in rules if matches(r, args.doctype, args.stage)]
    # Sort: blocking first, then by name
    filtered.sort(key=lambda r: (0 if r.get("severity") == "blocking" else 1, r.get("name", "")))

    if args.format == "json":
        import json
        print(json.dumps(filtered, indent=2))
    elif args.format == "names":
        print("\n".join(r["name"] for r in filtered))
    else:
        # manifest
        lines = []
        for r in filtered:
            sev = r.get("severity", "advisory")
            name = r.get("name", "")
            desc = r.get("description", "")
            lines.append(f"  [{sev}] {name} — {desc}")
        if not lines:
            print(f"(no rules apply for doctype={args.doctype} stage={args.stage})")
        else:
            print("\n".join(lines))

if __name__ == "__main__":
    main()
