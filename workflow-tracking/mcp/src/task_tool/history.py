"""Append-only history logger for the task-tool.

Provides functions for creating history entries with monotonic sequence
numbering and UTC timestamps. History entries are never modified or
deleted once created.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import HistoryEntry


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_entry(
    seq: int,
    operation: str,
    params: dict[str, Any],
) -> HistoryEntry:
    """Create a new history entry with the next monotonic sequence number.

    Args:
        seq: Monotonic sequence number (must be > all existing entries).
        operation: Operation type. Phase 1-4 operations: init, advance,
            record_output, mark_blocked, reset_to, override_transition.
            Phase 5 operations (AC-oriented workflow tracking; MR4-MR7):
            register_workflow, record_branch_arrival, record_review_evidence,
            accumulate_ac, advance_without_evidence.
        params: Operation-specific parameters.

    Returns:
        A new HistoryEntry.
    """
    return HistoryEntry(
        seq=seq,
        timestamp=_now_iso(),
        operation=operation,
        params=params,
    )


def next_seq(history: list[HistoryEntry]) -> int:
    """Return the next monotonic sequence number."""
    if not history:
        return 1
    return history[-1].seq + 1
