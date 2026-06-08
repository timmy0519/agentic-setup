"""Phase 1 acceptance tests for the task-tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from task_tool.yaml_parser import parse_workflow_yaml
from task_tool.validator import validate_graph
from task_tool.state import init_state, advance, get_current_state, get_legal_transitions, _state_path
from task_tool.errors import (
    INVALID_STRUCTURE,
    CAPABILITY_MISMATCH,
    ILLEGAL_TRANSITION,
    ALREADY_INITIALIZED,
)
from task_tool.models import StateDefinition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _parse_and_validate(yaml_str: str, capabilities: list[str]):
    """Parse YAML and validate graph. Returns (graph, error)."""
    result = parse_workflow_yaml(yaml_str)
    if isinstance(result, dict) and "ok" in result and not result["ok"]:
        return None, result
    error = validate_graph(result, capabilities)
    if error is not None:
        return None, error
    return result, None


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path, monkeypatch):
    """Each test runs in its own temp directory so state files don't collide."""
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# AC 1: Init with valid 3-state workflow
# ---------------------------------------------------------------------------

class TestAC1_InitValid:
    def test_init_creates_json_file(self):
        graph, err = _parse_and_validate(VALID_3STATE_YAML, ["self"])
        assert err is None, f"Unexpected parse/validate error: {err}"

        result = init_state(["self"], graph)
        assert result["ok"] is True, f"init_state failed: {result}"

        # JSON file exists
        state_path = _state_path()
        assert state_path.exists(), f"State file not created at {state_path}"

        data = json.loads(state_path.read_text())

        # meta.capabilities
        assert data["meta"]["capabilities"] == ["self"]

        # workflow.states has 3 states
        assert set(
            data["workflows"]["artifact-flow"]["workflow"]["states"].keys()
        ) == {"start", "middle", "end"}

        # position.current_state == first state
        assert (
            data["workflows"]["artifact-flow"]["position"]["current_state"] == "start"
        )


# ---------------------------------------------------------------------------
# AC 2: Init with handler type not in capabilities
# ---------------------------------------------------------------------------

class TestAC2_CapabilityMismatch:
    def test_handler_not_in_capabilities(self):
        yaml_str = """\
states:
  draft:
    handler_type: agent
    transitions:
      - review
    input: "Initial draft input"
    output: "Draft ready for review"
  review:
    handler_type: human
    transitions: []
    input: "Draft from draft state"
    output: "Final reviewed result"
"""
        graph, err = _parse_and_validate(yaml_str, ["agent"])
        # validator should catch 'human' not in capabilities
        if err is not None:
            error = err
        else:
            # If parse_and_validate didn't catch it, try init
            error = init_state(["agent"], graph)

        assert error["ok"] is False
        assert error["error"]["code"] == CAPABILITY_MISMATCH

        details = error["error"].get("details", {})
        # Should mention what was required vs declared
        assert "handler_type" in details or "capabilities" in details, (
            f"Error details should list required vs declared: {details}"
        )


# ---------------------------------------------------------------------------
# AC 3: Init with malformed YAML (dangling transition)
# ---------------------------------------------------------------------------

class TestAC3_DanglingTransition:
    def test_dangling_transition_target(self):
        yaml_str = """\
states:
  start:
    handler_type: self
    transitions:
      - nonexistent
    input: "Initial state"
    output: "Ready for next"
"""
        graph, err = _parse_and_validate(yaml_str, ["self"])

        if err is not None:
            error = err
        else:
            # graph parsed fine, but validator should catch it
            error = validate_graph(graph, ["self"])

        assert error is not None, "Expected error for dangling transition"
        assert error["ok"] is False
        assert error["error"]["code"] == INVALID_STRUCTURE

        # Should mention the dangling target
        msg = error["error"]["message"]
        details = error["error"].get("details", {})
        assert "nonexistent" in msg or "nonexistent" in str(details), (
            f"Error should mention dangling target 'nonexistent': {error}"
        )


# ---------------------------------------------------------------------------
# AC 4: Init with zero states
# ---------------------------------------------------------------------------

class TestAC4_ZeroStates:
    def test_zero_states(self):
        yaml_str = """\
states: {}
"""
        result = parse_workflow_yaml(yaml_str)

        # Parser should reject empty states
        if isinstance(result, dict) and "ok" in result and not result["ok"]:
            error = result
        else:
            # If parser allowed it, validator should catch it
            error = validate_graph(result, [])

        assert error is not None
        assert error["ok"] is False
        assert error["error"]["code"] == INVALID_STRUCTURE


# ---------------------------------------------------------------------------
# AC 5: Init called twice
# ---------------------------------------------------------------------------

class TestAC5_AlreadyInitialized:
    def test_double_init(self):
        graph, err = _parse_and_validate(VALID_3STATE_YAML, ["self"])
        assert err is None

        result1 = init_state(["self"], graph)
        assert result1["ok"] is True

        result2 = init_state(["self"], graph)
        assert result2["ok"] is False
        assert result2["error"]["code"] == ALREADY_INITIALIZED


# ---------------------------------------------------------------------------
# AC 6: Advance to legal target
# ---------------------------------------------------------------------------

class TestAC6_AdvanceLegal:
    def test_advance_updates_state(self):
        graph, err = _parse_and_validate(VALID_3STATE_YAML, ["self"])
        assert err is None

        init_state(["self"], graph)
        result = advance("middle")

        assert result["ok"] is True
        assert result["data"]["current_state"] == "middle"
        assert result["data"]["previous_state"] == "start"

        # Verify JSON file reflects new state
        data = json.loads(_state_path().read_text())
        assert data["workflows"]["artifact-flow"]["position"]["current_state"] == "middle"


# ---------------------------------------------------------------------------
# AC 7: Advance to non-legal target
# ---------------------------------------------------------------------------

class TestAC7_IllegalTransition:
    def test_advance_to_illegal_target(self):
        graph, err = _parse_and_validate(VALID_3STATE_YAML, ["self"])
        assert err is None

        init_state(["self"], graph)
        # From 'start', only 'middle' is legal — try 'end' directly
        result = advance("end")

        assert result["ok"] is False
        assert result["error"]["code"] == ILLEGAL_TRANSITION

        details = result["error"].get("details", {})
        assert "legal_transitions" in details, (
            f"Error should list legal transitions: {details}"
        )
        assert "middle" in details["legal_transitions"]


# ---------------------------------------------------------------------------
# AC 8: view_legal_transitions
# ---------------------------------------------------------------------------

class TestAC8_ViewLegalTransitions:
    def test_legal_transitions_from_start(self):
        graph, err = _parse_and_validate(VALID_3STATE_YAML, ["self"])
        assert err is None
        init_state(["self"], graph)

        result = get_legal_transitions()
        assert result["ok"] is True
        assert result["data"]["current_state"] == "start"
        assert result["data"]["transitions"] == ["middle"]

    def test_legal_transitions_from_end(self):
        graph, err = _parse_and_validate(VALID_3STATE_YAML, ["self"])
        assert err is None
        init_state(["self"], graph)
        advance("middle")
        advance("end")

        result = get_legal_transitions()
        assert result["ok"] is True
        assert result["data"]["current_state"] == "end"
        assert result["data"]["transitions"] == []


# ---------------------------------------------------------------------------
# AC 9: view_current_state
# ---------------------------------------------------------------------------

class TestAC9_ViewCurrentState:
    def test_current_state_after_init(self):
        graph, err = _parse_and_validate(VALID_3STATE_YAML, ["self"])
        assert err is None
        init_state(["self"], graph)

        result = get_current_state()
        assert result["ok"] is True
        assert result["data"]["current_state"] == "start"

    def test_current_state_after_advance(self):
        graph, err = _parse_and_validate(VALID_3STATE_YAML, ["self"])
        assert err is None
        init_state(["self"], graph)
        advance("middle")

        result = get_current_state()
        assert result["ok"] is True
        assert result["data"]["current_state"] == "middle"


# ---------------------------------------------------------------------------
# AC 10: Walk a 3-state linear workflow start to finish
# ---------------------------------------------------------------------------

class TestAC10_FullWalk:
    def test_walk_start_to_finish(self):
        graph, err = _parse_and_validate(VALID_3STATE_YAML, ["self"])
        assert err is None

        init_result = init_state(["self"], graph)
        assert init_result["ok"] is True
        assert init_result["data"]["current_state"] == "start"

        # Advance start -> middle
        r1 = advance("middle")
        assert r1["ok"] is True
        assert r1["data"]["current_state"] == "middle"
        assert r1["data"]["transitions"] == ["end"]

        # Advance middle -> end
        r2 = advance("end")
        assert r2["ok"] is True
        assert r2["data"]["current_state"] == "end"
        assert r2["data"]["transitions"] == []

        # Verify final state in file
        data = json.loads(_state_path().read_text())
        assert data["workflows"]["artifact-flow"]["position"]["current_state"] == "end"

        # End state has no legal transitions
        legal = get_legal_transitions()
        assert legal["ok"] is True
        assert legal["data"]["transitions"] == []
