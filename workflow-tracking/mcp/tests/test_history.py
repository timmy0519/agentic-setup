"""Unit tests for append-only history invariants."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from task_tool.yaml_parser import parse_workflow_yaml
from task_tool.validator import validate_graph
from task_tool.state import (
    init_state,
    advance,
    record_output,
    mark_blocked,
    reset_to,
    override_transition,
    update_workflow,
    _state_path,
)
from task_tool.history import make_entry, next_seq
from task_tool.models import HistoryEntry


VALID_YAML = """\
states:
  start:
    handler_type: self
    transitions:
      - middle
    input: "Initial state"
    output: "Ready for middle"
  middle:
    handler_type: self
    transitions:
      - start
      - end
    input: "Output from start"
    output: "Ready for end or back to start"
  end:
    handler_type: self
    transitions: []
    input: "Output from middle"
    output: "Final result"
"""


def _init():
    graph = parse_workflow_yaml(VALID_YAML)
    validate_graph(graph, ["self"])
    return init_state(["self"], graph)


def _read_history() -> list[dict]:
    data = json.loads(_state_path().read_text())
    return data["history"]


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# Append-only invariant
# ---------------------------------------------------------------------------

class TestAppendOnly:
    def test_history_grows_never_shrinks(self):
        _init()
        counts = [len(_read_history())]

        advance("middle")
        counts.append(len(_read_history()))

        record_output("middle", "spec.md")
        counts.append(len(_read_history()))

        advance("end")
        counts.append(len(_read_history()))

        # Each operation adds exactly one entry
        for i in range(1, len(counts)):
            assert counts[i] == counts[i - 1] + 1

    def test_existing_entries_unchanged(self):
        _init()
        h1 = _read_history()

        advance("middle")
        h2 = _read_history()

        # First entry unchanged
        assert h1[0] == h2[0]

        advance("end")
        h3 = _read_history()

        # First two entries unchanged
        assert h2[0] == h3[0]
        assert h2[1] == h3[1]


# ---------------------------------------------------------------------------
# Monotonic sequencing
# ---------------------------------------------------------------------------

class TestMonotonicSequence:
    def test_sequences_are_strictly_increasing(self):
        _init()
        advance("middle")
        record_output("middle", "artifact.md")
        advance("end")

        history = _read_history()
        seqs = [h["seq"] for h in history]
        for i in range(1, len(seqs)):
            assert seqs[i] == seqs[i - 1] + 1

    def test_first_seq_is_one(self):
        _init()
        history = _read_history()
        assert history[0]["seq"] == 1


class TestNextSeq:
    def test_empty_history_returns_one(self):
        assert next_seq([]) == 1

    def test_returns_next_after_last(self):
        entries = [
            HistoryEntry(seq=1, timestamp="t", operation="init", params={}),
            HistoryEntry(seq=2, timestamp="t", operation="advance", params={}),
        ]
        assert next_seq(entries) == 3


# ---------------------------------------------------------------------------
# Entry format for each operation type
# ---------------------------------------------------------------------------

class TestEntryFormats:
    def test_init_entry(self):
        _init()
        entry = _read_history()[0]
        assert entry["operation"] == "init"
        assert "capabilities" in entry["params"]
        assert "starting_state" in entry["params"]
        assert "state_count" in entry["params"]

    def test_advance_entry(self):
        _init()
        advance("middle")
        entry = _read_history()[1]
        assert entry["operation"] == "advance"
        assert entry["params"]["from"] == "start"
        assert entry["params"]["to"] == "middle"

    def test_record_output_entry(self):
        _init()
        record_output("start", "spec.md")
        entry = _read_history()[1]
        assert entry["operation"] == "record_output"
        assert entry["params"]["state"] == "start"
        assert entry["params"]["output_ref"] == "spec.md"

    def test_mark_blocked_entry(self):
        _init()
        mark_blocked("needs review", "reviewer available", "design blocked")
        entry = _read_history()[1]
        assert entry["operation"] == "mark_blocked"
        assert entry["params"]["blocker"] == "needs review"
        assert entry["params"]["unblock_condition"] == "reviewer available"
        assert entry["params"]["impact"] == "design blocked"

    def test_reset_to_entry(self):
        _init()
        advance("middle")
        reset_to("start", "scope changed", "need to rework design")
        entry = _read_history()[2]
        assert entry["operation"] == "reset_to"
        assert entry["params"]["from"] == "middle"
        assert entry["params"]["to"] == "start"
        assert entry["params"]["trigger"] == "scope changed"
        assert entry["params"]["context"] == "need to rework design"

    def test_override_transition_entry(self):
        _init()
        override_transition("end", "emergency", ["middle"], "skipping review")
        entry = _read_history()[1]
        assert entry["operation"] == "override_transition"
        assert entry["params"]["reason"] == "emergency"
        assert entry["params"]["skipped_alternatives"] == ["middle"]
        assert entry["params"]["risks"] == "skipping review"

    def test_update_workflow_entry(self):
        _init()
        new_yaml = """\
states:
  start:
    handler_type: self
    transitions:
      - done
    input: "Initial state"
    output: "Ready for done"
  done:
    handler_type: self
    transitions: []
    input: "Output from start"
    output: "Final result"
"""
        update_workflow(new_yaml, "simplify")
        entry = _read_history()[1]
        assert entry["operation"] == "update_workflow"
        assert entry["params"]["reason"] == "simplify"
        assert entry["params"]["old_version"] == 1
        assert entry["params"]["new_version"] == 2


# ---------------------------------------------------------------------------
# Timestamp ordering
# ---------------------------------------------------------------------------

class TestTimestampOrdering:
    def test_timestamps_are_non_decreasing(self):
        _init()
        advance("middle")
        advance("end")

        history = _read_history()
        timestamps = [h["timestamp"] for h in history]
        for i in range(1, len(timestamps)):
            t_prev = datetime.fromisoformat(timestamps[i - 1])
            t_curr = datetime.fromisoformat(timestamps[i])
            assert t_curr >= t_prev

    def test_timestamps_are_iso8601(self):
        _init()
        history = _read_history()
        for entry in history:
            # Should not raise
            datetime.fromisoformat(entry["timestamp"])


class TestMakeEntry:
    def test_returns_history_entry(self):
        entry = make_entry(seq=5, operation="advance", params={"from": "a", "to": "b"})
        assert isinstance(entry, HistoryEntry)
        assert entry.seq == 5
        assert entry.operation == "advance"
        assert entry.params == {"from": "a", "to": "b"}
        # Has a valid timestamp
        datetime.fromisoformat(entry.timestamp)
