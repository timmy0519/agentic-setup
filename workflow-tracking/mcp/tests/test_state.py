"""Unit tests for state operations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from task_tool.yaml_parser import parse_workflow_yaml
from task_tool.validator import validate_graph
from task_tool.state import (
    init_state,
    advance,
    mark_blocked,
    reset_to,
    record_output,
    update_workflow,
    _state_path,
    _reset_session,
)
from task_tool.errors import (
    ILLEGAL_TRANSITION,
    POSITION_BLOCKED,
    STATE_NOT_FOUND,
    STATE_NOT_VISITED,
)


VALID_3STATE_YAML = """\
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
      - end
    input: "Output from start"
    output: "Ready for end"
  end:
    handler_type: self
    transitions: []
    input: "Output from middle"
    output: "Final result"
"""


def _init_workflow(yaml_str: str = VALID_3STATE_YAML, capabilities: list[str] | None = None):
    """Helper: parse, validate, init. Returns init result."""
    caps = capabilities or ["self"]
    graph = parse_workflow_yaml(yaml_str)
    assert not (isinstance(graph, dict) and "ok" in graph and not graph["ok"]), graph
    err = validate_graph(graph, caps)
    assert err is None, err
    return init_state(caps, graph)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# Advance
# ---------------------------------------------------------------------------

class TestAdvanceLegal:
    def test_advance_updates_position(self):
        _init_workflow()
        result = advance("middle")
        assert result["ok"] is True
        assert result["data"]["current_state"] == "middle"
        assert result["data"]["previous_state"] == "start"

    def test_advance_persists_to_file(self):
        _init_workflow()
        advance("middle")
        data = json.loads(_state_path().read_text())
        assert data["workflows"]["artifact-flow"]["position"]["current_state"] == "middle"


class TestAdvanceIllegal:
    def test_skip_state_rejected(self):
        _init_workflow()
        result = advance("end")
        assert result["ok"] is False
        assert result["error"]["code"] == ILLEGAL_TRANSITION
        assert "middle" in result["error"]["details"]["legal_transitions"]


# ---------------------------------------------------------------------------
# mark_blocked + advance rejection
# ---------------------------------------------------------------------------

class TestBlockedAdvance:
    def test_advance_while_blocked_rejected(self):
        _init_workflow()
        mark_blocked("dependency missing", "dependency deployed", "design work stalled")
        result = advance("middle")
        assert result["ok"] is False
        assert result["error"]["code"] == POSITION_BLOCKED
        assert "dependency missing" in result["error"]["message"]


# ---------------------------------------------------------------------------
# reset_to
# ---------------------------------------------------------------------------

class TestResetTo:
    def test_reset_to_valid_state(self):
        _init_workflow()
        advance("middle")
        result = reset_to("start", "rework needed", "design had gaps")
        assert result["ok"] is True
        assert result["data"]["current_state"] == "start"

    def test_reset_clears_blocked(self):
        _init_workflow()
        mark_blocked("stuck", "get unstuck", "nothing moves")
        result = reset_to("start", "cleared by reset", "issue resolved")
        assert result["ok"] is True
        assert result["data"]["blocked_cleared"] is True

    def test_reset_to_nonexistent(self):
        _init_workflow()
        result = reset_to("phantom", "test trigger", "test context")
        assert result["ok"] is False
        assert result["error"]["code"] == STATE_NOT_FOUND


# ---------------------------------------------------------------------------
# record_output
# ---------------------------------------------------------------------------

class TestRecordOutput:
    def test_record_on_visited_state(self):
        _init_workflow()
        result = record_output("start", "artifacts/spec.md")
        assert result["ok"] is True
        assert result["data"]["output"]["ref"] == "artifacts/spec.md"
        assert "recorded_at" in result["data"]["output"]

    def test_record_on_unvisited_state(self):
        _init_workflow()
        result = record_output("middle", "artifacts/spec.md")
        assert result["ok"] is False
        assert result["error"]["code"] == STATE_NOT_VISITED

    def test_record_on_nonexistent_state(self):
        _init_workflow()
        result = record_output("nope", "artifacts/spec.md")
        assert result["ok"] is False
        assert result["error"]["code"] == STATE_NOT_FOUND


# ---------------------------------------------------------------------------
# Atomic file write
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_state_file_exists_after_init(self):
        _init_workflow()
        path = _state_path()
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["meta"]["schema_version"] == 2

    def test_state_file_valid_json_after_advance(self):
        _init_workflow()
        advance("middle")
        data = json.loads(_state_path().read_text())
        assert data["workflows"]["artifact-flow"]["position"]["current_state"] == "middle"


# ---------------------------------------------------------------------------
# Output orphaning via update_workflow
# ---------------------------------------------------------------------------

class TestOutputOrphaning:
    def test_orphaned_outputs_removed_from_position(self):
        _init_workflow()
        record_output("start", "old-artifact.md")
        advance("middle")

        # Update workflow: remove 'start' state, reset to 'alpha'
        new_yaml = """\
states:
  alpha:
    handler_type: self
    transitions:
      - middle
    input: "Initial state"
    output: "Ready for middle"
  middle:
    handler_type: self
    transitions:
      - end
    input: "Output from alpha"
    output: "Ready for end"
  end:
    handler_type: self
    transitions: []
    input: "Output from middle"
    output: "Final result"
"""
        result = update_workflow(new_yaml, "restructure", reset_to_state="alpha")
        assert result["ok"] is True

        # Outputs for removed state no longer in position
        data = json.loads(_state_path().read_text())
        assert "start" not in data["workflows"]["artifact-flow"]["position"]["outputs"]

        # But orphaned outputs appear in history
        history = data["history"]
        update_entry = [h for h in history if h["operation"] == "update_workflow"][0]
        assert "orphaned_outputs" in update_entry["params"]
        assert "start" in update_entry["params"]["orphaned_outputs"]
