#!/usr/bin/env python3
"""cache.py — Content-hash cache for verify results.

Two modes:
    check <artifact_path>   — compute SHA-256, read .verify-cache.json, return hit/miss
    update <artifact_path> <phase> <verdict>  — write hash + verdict + timestamp

Cache file: .verify-cache.json in the same directory as the artifact.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def compute_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file content."""
    content = file_path.read_bytes()
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def get_cache_path(artifact_path: Path) -> Path:
    """Cache file lives in the same directory as the artifact."""
    return artifact_path.parent / ".verify-cache.json"


def load_cache(cache_path: Path) -> dict:
    """Load cache file. Returns empty dict on missing/corrupted."""
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache_path: Path, cache: dict):
    """Write cache file."""
    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=2)


def check(artifact_path: Path):
    """Check cache status for an artifact."""
    if not artifact_path.exists():
        print(json.dumps({"error": f"Artifact not found: {artifact_path}"}))
        sys.exit(1)

    current_hash = compute_hash(artifact_path)
    cache_path = get_cache_path(artifact_path)
    cache = load_cache(cache_path)

    filename = artifact_path.name
    entry = cache.get(filename, {})

    if entry.get("hash") == current_hash:
        # Cache hit — return stored verdicts
        result = {
            "hit": True,
            "hash": current_hash,
            "structural": entry.get("structural", {}).get("verdict"),
            "quality": entry.get("quality", {}).get("verdict"),
        }
    else:
        result = {
            "hit": False,
            "hash": current_hash,
            "structural": None,
            "quality": None,
        }

    print(json.dumps(result, indent=2))


def update(artifact_path: Path, phase: str, verdict: str):
    """Update cache for a specific phase."""
    if phase not in ("structural", "quality"):
        print(json.dumps({"error": f"Invalid phase: {phase}. Must be 'structural' or 'quality'."}))
        sys.exit(1)

    current_hash = compute_hash(artifact_path)
    cache_path = get_cache_path(artifact_path)
    cache = load_cache(cache_path)

    filename = artifact_path.name
    if filename not in cache:
        cache[filename] = {"hash": current_hash}

    cache[filename]["hash"] = current_hash
    cache[filename][phase] = {
        "verdict": verdict,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    save_cache(cache_path, cache)
    print(json.dumps({"ok": True, "file": filename, "phase": phase, "verdict": verdict}))


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: cache.py check <artifact_path> | cache.py update <artifact_path> <phase> <verdict>"}))
        sys.exit(1)

    mode = sys.argv[1]
    artifact_path = Path(sys.argv[2]).resolve()

    if mode == "check":
        check(artifact_path)
    elif mode == "update":
        if len(sys.argv) < 5:
            print(json.dumps({"error": "Usage: cache.py update <artifact_path> <phase> <verdict>"}))
            sys.exit(1)
        phase = sys.argv[3]
        verdict = sys.argv[4]
        update(artifact_path, phase, verdict)
    else:
        print(json.dumps({"error": f"Unknown mode: {mode}. Use 'check' or 'update'."}))
        sys.exit(1)


if __name__ == "__main__":
    main()
