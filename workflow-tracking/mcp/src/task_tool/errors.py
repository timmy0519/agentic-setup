"""Structured error responses for the task-tool."""

from __future__ import annotations

from typing import Any


# Phase 1 error codes
INVALID_STRUCTURE = "INVALID_STRUCTURE"
CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"
NO_WORKFLOW = "NO_WORKFLOW"
ALREADY_INITIALIZED = "ALREADY_INITIALIZED"

# Phase 2 error codes
STATE_NOT_FOUND = "STATE_NOT_FOUND"
STATE_NOT_VISITED = "STATE_NOT_VISITED"

# Phase 3 error codes
POSITION_BLOCKED = "POSITION_BLOCKED"
REASON_REQUIRED = "REASON_REQUIRED"

# Phase 4 error codes
CURRENT_STATE_REMOVED = "CURRENT_STATE_REMOVED"
VERSION_NOT_FOUND = "VERSION_NOT_FOUND"

# Phase 5 error codes (AC-oriented workflow tracking; MR4-MR7)
WORKFLOW_NOT_REGISTERED = "WORKFLOW_NOT_REGISTERED"
META_KEY_EXISTS = "META_KEY_EXISTS"
JOIN_STATE_REQUIRED = "JOIN_STATE_REQUIRED"
BRANCH_UNKNOWN = "BRANCH_UNKNOWN"
NOT_A_GATE = "NOT_A_GATE"
AC_IDENTITY_REQUIRED = "AC_IDENTITY_REQUIRED"


def make_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    guidance: str = "",
) -> dict:
    """Create a structured error response.

    Returns:
        {"ok": false, "error": {"code": ..., "message": ..., "details": ..., "guidance": ...}}
    """
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "guidance": guidance,
        },
    }


def make_success(data: dict[str, Any]) -> dict:
    """Create a structured success response.

    Returns:
        {"ok": true, "data": {...}}
    """
    return {"ok": True, "data": data}
