#!/usr/bin/env python3
"""report.py — Structured finding reporter.

Called by rule subagents to self-report findings, or by the orchestrator
to normalize NL output into structured JSON.

Usage (subagent self-report):
    python3 report.py --rule-id no-vague-language \
                      --verdict FAIL \
                      --evidence "Line 42: 'we should consider' — tentative phrasing" \
                      --severity blocking

Usage (orchestrator normalize from NL):
    echo "some NL output" | python3 report.py --parse

Output:
    {"rule_id": "no-vague-language", "verdict": "FAIL", "severity": "blocking",
     "evidence": "Line 42: ...", "confidence": "HIGH"}
"""

from __future__ import annotations

import json
import re
import sys
from typing import Optional


VALID_VERDICTS = {"PASS", "FAIL", "CONSIDER", "SKIP"}
VALID_SEVERITIES = {"blocking", "advisory"}
VALID_CONFIDENCES = {"HIGH", "MEDIUM", "LOW"}


def self_report(rule_id: str, verdict: str, evidence: str,
                severity: str = "blocking", confidence: str = "HIGH") -> dict:
    """Structured self-report from a subagent."""
    verdict = verdict.upper().strip()
    severity = severity.lower().strip()
    confidence = confidence.upper().strip()

    if verdict not in VALID_VERDICTS:
        verdict = "FAIL"  # safe default
    if severity not in VALID_SEVERITIES:
        severity = "blocking"
    if confidence not in VALID_CONFIDENCES:
        confidence = "MEDIUM"

    return {
        "rule_id": rule_id,
        "verdict": verdict,
        "severity": severity,
        "evidence": evidence.strip(),
        "confidence": confidence,
    }


def parse_nl(text: str) -> dict:
    """Tolerant parse of NL subagent output into structured finding.

    Looks for labeled fields first (VERDICT:, RULE:, EVIDENCE:),
    falls back to keyword scanning.
    """
    result = {
        "rule_id": None,
        "verdict": None,
        "severity": None,
        "evidence": None,
        "confidence": None,
        "parse_method": "nl_fallback",
    }

    # Try labeled fields first
    rule_match = re.search(r'RULE:\s*(.+)', text, re.IGNORECASE)
    if rule_match:
        result["rule_id"] = rule_match.group(1).strip()

    verdict_match = re.search(r'VERDICT:\s*(PASS|FAIL|CONSIDER|SKIP)', text, re.IGNORECASE)
    if verdict_match:
        result["verdict"] = verdict_match.group(1).upper()
        result["parse_method"] = "labeled_field"

    severity_match = re.search(r'SEVERITY:\s*(blocking|advisory)', text, re.IGNORECASE)
    if severity_match:
        result["severity"] = severity_match.group(1).lower()

    confidence_match = re.search(r'CONFIDENCE:\s*(HIGH|MEDIUM|LOW)', text, re.IGNORECASE)
    if confidence_match:
        result["confidence"] = confidence_match.group(1).upper()

    evidence_match = re.search(r'EVIDENCE:\s*(.+?)(?=\n(?:VERDICT|SEVERITY|CONFIDENCE|RULE):|$)',
                                text, re.IGNORECASE | re.DOTALL)
    if evidence_match:
        result["evidence"] = evidence_match.group(1).strip()

    # Fallback: scan for verdict keywords if labeled field not found
    if not result["verdict"]:
        # Use last occurrence of a verdict keyword (most likely the final determination)
        for match in re.finditer(r'\b(PASS|FAIL|CONSIDER)\b', text, re.IGNORECASE):
            result["verdict"] = match.group(1).upper()
        if result["verdict"]:
            result["parse_method"] = "keyword_scan"

    # If still no verdict, mark as unparseable
    if not result["verdict"]:
        result["verdict"] = "FAIL"
        result["evidence"] = result.get("evidence") or "evaluation error: no verdict returned"
        result["parse_method"] = "no_verdict_found"

    return result


def main():
    if "--parse" in sys.argv:
        # Orchestrator mode: parse NL from stdin
        text = sys.stdin.read()
        result = parse_nl(text)
        print(json.dumps(result, indent=2))
        return

    # Subagent self-report mode
    args = {}
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--rule-id" and i + 1 < len(sys.argv):
            args["rule_id"] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--verdict" and i + 1 < len(sys.argv):
            args["verdict"] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--evidence" and i + 1 < len(sys.argv):
            args["evidence"] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--severity" and i + 1 < len(sys.argv):
            args["severity"] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--confidence" and i + 1 < len(sys.argv):
            args["confidence"] = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    required = {"rule_id", "verdict", "evidence"}
    missing = required - args.keys()
    if missing:
        print(json.dumps({"error": f"Missing required args: {missing}. Usage: report.py --rule-id ID --verdict PASS|FAIL|CONSIDER --evidence '...'"}))
        sys.exit(1)

    result = self_report(**args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
