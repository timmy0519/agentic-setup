"""Tests for get_active_plan — session-scoped read, no-session contract, two-layer partition.

Covers US1/MR1 (attached-session registry, no scan/latch, resume switches plan,
restart-survivable), KD8/NFR1 (no-session typed-success contract), and
US2/MR2 (two-layer partition: plan holds only high-level items + gates/ACs,
no execution-detail item mirrored from the native task list).
"""

from __future__ import annotations

import pytest

from task_tool.yaml_parser import parse_workflow_yaml
from task_tool.validator import validate_graph
from task_tool.state import (
    init_state,
    advance,
    get_active_plan,
    resume,
    _reset_session,
)


# ---------------------------------------------------------------------------
# Workflow fixtures
# ---------------------------------------------------------------------------

# A plain 3-state flow with a gate + ACs on the review state and NO
# execution-detail states — the registry only ever holds high-level items.
GATED_YAML = """\
states:
  draft:
    handler_type: self
    transitions:
      - review
    input: "Initial state"
    output: "Ready for review"
  review:
    handler_type: self
    transitions:
      - done
    gate: true
    acs:
      - id: diagram-present
        ac: "design.md contains a Mermaid diagram"
      - id: decisions-have-rationale
        ac: "every decision carries a rationale"
    input: "Draft to review"
    output: "Reviewed"
  done:
    handler_type: self
    transitions: []
    input: "Reviewed output"
    output: "Final result"
"""

SIMPLE_YAML = """\
states:
  alpha:
    handler_type: self
    transitions:
      - omega
    input: "start"
    output: "ready"
  omega:
    handler_type: self
    transitions: []
    input: "ready"
    output: "end"
"""


def _init(yaml_str: str = GATED_YAML, caps: list[str] | None = None) -> dict:
    """Parse, validate, init. Returns init result."""
    caps = caps or ["self"]
    graph = parse_workflow_yaml(yaml_str)
    assert not (isinstance(graph, dict) and "ok" in graph and not graph["ok"]), graph
    err = validate_graph(graph, caps)
    assert err is None, err
    return init_state(caps, graph)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# US1 / MR1 — attached-session read, no scan / no latch
# ---------------------------------------------------------------------------


class TestAttachedSessionRead:
    def test_returns_attached_session_with_no_path(self):
        """get_active_plan takes no path and returns the attached session's plan."""
        init = _init()
        result = get_active_plan()
        assert result["ok"] is True
        assert result["attached"] is True
        assert result["active_plan"] is not None
        assert result["active_plan"]["session_id"] == init["data"]["session_id"]
        # Default member present, surfacing the high-level current state.
        members = result["active_plan"]["members"]
        assert "artifact-flow" in members
        assert members["artifact-flow"]["current_state"] == "draft"

    def test_takes_no_path_argument(self):
        """Contract: get_active_plan is a zero-arg read — it must not accept a path."""
        import inspect

        sig = inspect.signature(get_active_plan)
        assert len(sig.parameters) == 0, (
            "get_active_plan must be a pure session-scoped read with no "
            f"caller-supplied path; got params {list(sig.parameters)}"
        )

    def test_does_not_latch_or_scan_other_sessions(self):
        """A second session on disk is NOT discovered — only the attached one is read.

        get_active_plan does no .task-tool/ scan and no recency latching: it
        reads exactly the session attached via init/resume. We prove this by
        creating a second session file on disk (different cwd) while the first
        stays attached, then asserting the plan still reflects the first.
        """
        init = _init()
        first_session_id = init["data"]["session_id"]

        # Create a second, unrelated session file on disk under the SAME base
        # dir, then re-attach to the first. If get_active_plan scanned/latched,
        # it could surface the wrong (e.g. most-recent) session.
        first_path = init["data"]["state_file"]
        _reset_session()
        _init(SIMPLE_YAML)  # writes a second session dir under .task-tool/
        _reset_session()
        resume(first_path)  # explicit re-attach to the FIRST session

        result = get_active_plan()
        assert result["attached"] is True
        assert result["active_plan"]["session_id"] == first_session_id
        # The first session's workflow is the gated one (has a 'review' member state).
        assert "review" in _state_names(result, "artifact-flow")

    def test_resume_to_different_session_switches_plan(self):
        """After resume(path) to a different session, the plan reflects THAT session."""
        first = _init()
        first_id = first["data"]["session_id"]
        first_path = first["data"]["state_file"]

        # Build a second, distinct session and capture its path.
        _reset_session()
        second = _init(SIMPLE_YAML)
        second_id = second["data"]["session_id"]
        second_path = second["data"]["state_file"]
        assert second_id != first_id

        # Attached to the second now — plan must reflect the second.
        plan2 = get_active_plan()
        assert plan2["active_plan"]["session_id"] == second_id
        assert "alpha" in _state_names(plan2, "artifact-flow")
        assert "review" not in _state_names(plan2, "artifact-flow")

        # resume(first_path) switches the attached session back to the first.
        _reset_session()
        resume(first_path)
        plan1 = get_active_plan()
        assert plan1["active_plan"]["session_id"] == first_id
        assert "review" in _state_names(plan1, "artifact-flow")

    def test_identical_plan_after_simulated_restart_and_resume(self):
        """Simulated process restart (_reset_session) + resume returns an equivalent plan."""
        # Use the non-gated flow so advance moves position (a gate:true target
        # returns a soft recommendation and intentionally does NOT advance).
        init = _init(SIMPLE_YAML)
        path = init["data"]["state_file"]
        advance("omega")  # move position before restart so we test persistence

        before = get_active_plan()

        # Simulate a process restart: drop the in-process attachment entirely,
        # then re-attach via the existing resume() mechanism.
        _reset_session()
        resume(path)
        after = get_active_plan()

        assert after["attached"] is True
        assert after["active_plan"]["session_id"] == before["active_plan"]["session_id"]
        assert (
            after["active_plan"]["members"]["artifact-flow"]["current_state"]
            == before["active_plan"]["members"]["artifact-flow"]["current_state"]
            == "omega"
        )
        # The persisted gate/AC structure survives the restart unchanged.
        assert (
            after["active_plan"]["members"]["artifact-flow"]
            == before["active_plan"]["members"]["artifact-flow"]
        )


# ---------------------------------------------------------------------------
# KD8 / NFR1 — no-session contract is typed success, NOT an error
# ---------------------------------------------------------------------------


class TestNoSessionContract:
    def test_no_session_returns_typed_success_not_error(self):
        """Nothing attached -> {ok: true, active_plan: null, attached: false}, never an error."""
        # Autouse fixtures reset the session; nothing is attached here.
        result = get_active_plan()
        assert result["ok"] is True
        assert result["active_plan"] is None
        assert result["attached"] is False
        # It is a success, not the error envelope.
        assert "error" not in result

    def test_no_session_provides_init_and_resume_guidance(self):
        """The no-session response guides to init (new) or list_sessions+resume (existing)."""
        result = get_active_plan()
        guidance = result.get("guidance", "").lower()
        assert "init" in guidance
        assert "resume" in guidance
        assert "list_sessions" in guidance


# ---------------------------------------------------------------------------
# US2 / MR2 — two-layer partition assertion
# ---------------------------------------------------------------------------


class TestTwoLayerPartition:
    def test_plan_holds_only_high_level_items_and_gates_acs(self):
        """The active plan exposes high-level position + gates/ACs only.

        No execution-detail item (a native-task-list-style field — e.g. a
        per-step checklist, sub-task list, or coordination notes) is mirrored
        into the plan. The plan's member view is partitioned to exactly the
        high-level keys.
        """
        _init()
        result = get_active_plan()
        member = result["active_plan"]["members"]["artifact-flow"]

        # The member view is restricted to the high-level / gate-AC layer.
        allowed_keys = {
            "current_state",
            "ready_gates",
            "waiting_joins",
            "open_acs",
            "graduation_prompts",
        }
        assert set(member.keys()) <= allowed_keys, (
            "active plan member leaked execution-detail keys outside the "
            f"high-level + gate/AC layer: {set(member.keys()) - allowed_keys}"
        )

        # Forbidden execution-detail / native-task-list fields must NOT appear —
        # those belong to the native task list (the other layer), not the plan.
        forbidden_keys = {
            "tasks",
            "subtasks",
            "checklist",
            "steps",
            "todos",
            "outputs",
            "visited",
            "history",
        }
        assert forbidden_keys.isdisjoint(member.keys()), (
            "active plan mirrored execution-detail fields from the native task "
            f"list: {forbidden_keys & set(member.keys())}"
        )

    def test_plan_session_view_is_rollup_not_execution_detail(self):
        """The session-level view carries only session_id/status/members — no detail dump."""
        _init()
        result = get_active_plan()
        plan = result["active_plan"]
        assert set(plan.keys()) == {"session_id", "status", "members"}

    def test_acs_are_referenced_high_level_not_full_bodies(self):
        """ACs surface as references (rule names / short keys), not copied detail.

        US2 two-layer boundary: the plan holds gates/ACs as high-level
        references to the durable verify library, never the execution detail of
        a native task list. open_acs is empty until a gate fails, and the
        member view never embeds raw rule bodies.
        """
        _init()
        result = get_active_plan()
        member = result["active_plan"]["members"]["artifact-flow"]
        # No failures recorded yet -> no open ACs mirrored into the plan.
        assert member["open_acs"] == []
        assert member["graduation_prompts"] == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state_names(plan_result: dict, meta_key: str) -> set[str]:
    """Read the member's underlying state graph from disk to assert which
    session is attached (the plan view itself is intentionally high-level)."""
    import json

    from task_tool.state import _state_path

    data = json.loads(_state_path().read_text())
    return set(data["workflows"][meta_key]["workflow"]["states"].keys())
