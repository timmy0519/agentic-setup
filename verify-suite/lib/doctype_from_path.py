#!/usr/bin/env python3
"""Detect artifact doctype from file path. Returns doctype string or empty (unknown)."""
import re
import sys

DOCTYPE_PATTERNS = [
    # Specs
    (r"/specs/[^/]+/requirements\.md$",           "spec-req"),
    (r"/specs/[^/]+/design\.md$",                 "spec-design"),
    (r"/specs/[^/]+/task\.md$",                   "spec-task"),
    (r"/specs/[^/]+/\.decisions\.md$",            "spec-decisions"),
    # Research
    (r"/Research/[^/]+\.md$",                     "research-note"),
    (r"/Research/[^/]+/[^/]+\.md$",               "research-note"),
    # Skills (self-referential)
    (r"\.claude/skills/[^/]+/SKILL\.md$",         "skill-def"),
    (r"\.claude/skills/[^/]+/references/.*\.md$", "skill-reference"),
    (r"\.claude/skills/verify/rules/.*\.md$",     "verify-rule"),
    # Memory
    (r"\.claude/projects/.*/memory/.*\.md$",      "memory"),
    # Project meta
    (r"/Projects/[^/]+/index\.md$",               "project-index"),
    (r"/Projects/[^/]+/WISHLIST\.md$",            "wishlist"),
    # Top-level
    (r"CLAUDE\.md$",                              "claude-md"),
    # Explicit exclusions (return empty string explicitly)
    (r"\.claude/settings.*\.json$",               ""),
    (r"\.claude/hooks/.*",                        ""),
    (r"\.git/.*",                                 ""),
]

def detect(path: str) -> str:
    for pattern, doctype in DOCTYPE_PATTERNS:
        if re.search(pattern, path):
            return doctype
    return ""

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("", end="")
        sys.exit(0)
    print(detect(sys.argv[1]), end="")
