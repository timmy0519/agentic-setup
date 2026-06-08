"""Unit tests for graph structure validation."""

from __future__ import annotations

from task_tool.validator import validate_graph
from task_tool.models import StateDefinition
from task_tool.errors import INVALID_STRUCTURE, CAPABILITY_MISMATCH


class TestZeroStates:
    def test_empty_graph_rejected(self):
        error = validate_graph({}, ["self"])
        assert error is not None
        assert error["ok"] is False
        assert error["error"]["code"] == INVALID_STRUCTURE
        assert "at least one" in error["error"]["message"].lower()


class TestDanglingTransitions:
    def test_transition_to_undefined_state(self):
        graph = {
            "start": StateDefinition(handler_type="self", transitions=["missing"], input="Initial state", output="Ready for next"),
        }
        error = validate_graph(graph, ["self"])
        assert error is not None
        assert error["ok"] is False
        assert error["error"]["code"] == INVALID_STRUCTURE
        assert "missing" in error["error"]["message"]

    def test_valid_transitions_accepted(self):
        graph = {
            "a": StateDefinition(handler_type="self", transitions=["b"], input="Initial state", output="Ready for b"),
            "b": StateDefinition(handler_type="self", transitions=[], input="Final input", output="Final result"),
        }
        assert validate_graph(graph, ["self"]) is None


class TestCyclesWithExits:
    def test_cycle_with_exit_accepted(self):
        graph = {
            "a": StateDefinition(handler_type="self", transitions=["b"], input="Initial state", output="Ready for b"),
            "b": StateDefinition(handler_type="self", transitions=["a", "c"], input="Output from a", output="Ready for a or c"),
            "c": StateDefinition(handler_type="self", transitions=[], input="Final input", output="Final result"),
        }
        assert validate_graph(graph, ["self"]) is None

    def test_cycle_without_exit_rejected(self):
        graph = {
            "a": StateDefinition(handler_type="self", transitions=["b"], input="Initial state", output="Ready for b"),
            "b": StateDefinition(handler_type="self", transitions=["a"], input="Output from a", output="Ready for a"),
        }
        error = validate_graph(graph, ["self"])
        assert error is not None
        assert error["ok"] is False
        assert error["error"]["code"] == INVALID_STRUCTURE
        assert "exit" in error["error"]["message"].lower()

    def test_self_loop_without_exit_rejected(self):
        graph = {
            "a": StateDefinition(handler_type="self", transitions=["a"], input="Output from a", output="Ready for a"),
        }
        error = validate_graph(graph, ["self"])
        assert error is not None
        assert error["error"]["code"] == INVALID_STRUCTURE

    def test_self_loop_with_exit_accepted(self):
        graph = {
            "a": StateDefinition(handler_type="self", transitions=["a", "b"], input="Initial state", output="Ready for a or b"),
            "b": StateDefinition(handler_type="self", transitions=[], input="Final input", output="Final result"),
        }
        assert validate_graph(graph, ["self"]) is None


class TestCapabilityMismatch:
    def test_handler_type_not_in_capabilities(self):
        graph = {
            "draft": StateDefinition(handler_type="agent", transitions=["review"], input="Initial draft", output="Draft ready"),
            "review": StateDefinition(handler_type="human", transitions=[], input="Draft from draft", output="Review complete"),
        }
        error = validate_graph(graph, ["agent"])
        assert error is not None
        assert error["ok"] is False
        assert error["error"]["code"] == CAPABILITY_MISMATCH
        assert "human" in error["error"]["message"]

    def test_all_handler_types_in_capabilities(self):
        graph = {
            "draft": StateDefinition(handler_type="agent", transitions=["review"], input="Initial draft", output="Draft ready"),
            "review": StateDefinition(handler_type="human", transitions=[], input="Draft from draft", output="Review complete"),
        }
        assert validate_graph(graph, ["agent", "human"]) is None

    def test_empty_capabilities_rejects_any_handler(self):
        graph = {
            "start": StateDefinition(handler_type="self", transitions=[], input="Final input", output="Final result"),
        }
        error = validate_graph(graph, [])
        assert error is not None
        assert error["error"]["code"] == CAPABILITY_MISMATCH
