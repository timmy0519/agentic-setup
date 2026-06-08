#!/usr/bin/env python3
"""gate.py — Structural gate check.

Accepts JSON array of structural verdict objects on stdin,
string-matches for FAIL, returns {pass: bool, fail_count: int}.

Usage:
    echo '[{"id": "rule-a", "verdict": "PASS"}, {"id": "rule-b", "verdict": "FAIL"}]' | python3 gate.py
"""

import json
import sys


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    if not isinstance(data, list):
        print(json.dumps({"error": "Expected JSON array of verdict objects"}))
        sys.exit(1)

    fail_count = 0
    for item in data:
        verdict = str(item.get("verdict", "")).upper()
        if verdict == "FAIL":
            fail_count += 1

    result = {
        "pass": fail_count == 0,
        "fail_count": fail_count,
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
