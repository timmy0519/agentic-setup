"""Join-tracking tests — fan-out branch arrival, convergence surfacing,
restart survival, and rework reset-on-reentry. (US7, MR7, KD3, KD4)"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from task_tool.yaml_parser import parse_workflow_yaml
from task_tool.validator import validate_graph
from task_tool.state import (
    init_state,
    advance,
    reset_to,
    override_transition,
    resume,
    record_branch_arrival,
    view_join_status,
    get_active_plan,
    get_current_state,
    _reset_session,
)
from task_tool.errors import BRANCH_UNKNOWN


# A workflow with a convergence state `converge` that requires three branches.
# `fanout` is a predecessor that feeds `converge`; a back-edge from `converge`
# returns to `fanout`, giving us a rework cycle to test reset-on-reentry.
JOIN_YAML = """\
states:
  start:
    handler_type: self
    transitions:
      - fanout
    input: "Initial"
    output: "Ready to fan out"
  fanout:
    handler_type: self
    transitions:
      - converge
    input: "Dispatch branches"
    output: "Branches dispatched"
  converge:
    handler_type: self
    transitions:
      - done
      - fanout
    join_required:
      - branch_a
      - branch_b
      - branch_c
    input: "Branch results"
    output: "Converged"
  done:
    handler_type: self
    transitions: []
    input: "Converged result"
    output: "Final"
"""


def _init_join_workflow():
    """Parse, validate, init the join workflow. Returns init result."""
    caps = ["self"]
    graph = parse_workflow_yaml(JOIN_YAML)
    assert not (isinstance(graph, dict) and "ok" in graph and not graph["ok"]), graph
    err = validate_graph(graph, caps)
    assert err is None, err
    return init_state(caps, graph)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# Declaration parses + arrival accumulates + waiting-on view (US7, MR7)
# ---------------------------------------------------------------------------

class TestJoinDeclarationAndArrival:
    def test_join_required_parses(self):
        graph = parse_workflow_yaml(JOIN_YAML)
        assert graph["converge"].join_required == ["branch_a", "branch_b", "branch_c"]

    def test_arrival_accumulates_received_branches(self):
        _init_join_workflow()
        r1 = record_branch_arrival("converge", "branch_a")
        assert r1["ok"] is True
        assert r1["data"]["received"] == ["branch_a"]
        assert set(r1["data"]["waiting_on"]) == {"branch_b", "branch_c"}
        assert r1["data"]["ready"] is False

        r2 = record_branch_arrival("converge", "branch_b")
        assert set(r2["data"]["received"]) == {"branch_a", "branch_b"}
        assert r2["data"]["waiting_on"] == ["branch_c"]
        assert r2["data"]["ready"] is False

    def test_view_join_status_names_missing_branches(self):
        _init_join_workflow()
        record_branch_arrival("converge", "branch_a")

        result = view_join_status()
        assert result["ok"] is True
        joins = result["data"]["joins"]
        assert len(joins) == 1
        conv = joins[0]
        assert conv["state"] == "converge"
        assert conv["received"] == ["branch_a"]
        assert set(conv["waiting_on"]) == {"branch_b", "branch_c"}
        assert conv["ready"] is False
        # "blocked, waiting on X" wording names the missing branches.
        assert "waiting on" in conv["status"]
        assert "branch_b" in conv["status"]
        assert "branch_c" in conv["status"]


# ---------------------------------------------------------------------------
# Idempotent arrival + unknown-label rejection (KD3, MR7)
# ---------------------------------------------------------------------------

class TestIdempotentAndUnknown:
    def test_duplicate_arrival_is_idempotent(self):
        _init_join_workflow()
        record_branch_arrival("converge", "branch_a")
        # Same label again — set semantics, received unchanged.
        r = record_branch_arrival("converge", "branch_a")
        assert r["ok"] is True
        assert r["data"]["received"] == ["branch_a"]
        assert r["data"]["received"].count("branch_a") == 1

        status = view_join_status()["data"]["joins"][0]
        assert status["received"] == ["branch_a"]

    def test_out_of_set_label_raises_branch_unknown(self):
        _init_join_workflow()
        r = record_branch_arrival("converge", "branch_z")
        assert r["ok"] is False
        assert r["error"]["code"] == BRANCH_UNKNOWN
        # Unknown label is never silently counted.
        status = view_join_status()["data"]["joins"][0]
        assert status["received"] == []
        assert "branch_z" not in status["received"]


# ---------------------------------------------------------------------------
# Convergence surfaced, NOT auto-advanced (KD3, KD4, MR7)
# ---------------------------------------------------------------------------

class TestConvergenceSurfacedNotAutoAdvanced:
    def test_all_branches_arrived_surfaces_ready_without_firing(self):
        _init_join_workflow()
        # Advance to the convergence state so it is the current position.
        advance("fanout")
        advance("converge")
        assert get_current_state()["data"]["current_state"] == "converge"

        record_branch_arrival("converge", "branch_a")
        record_branch_arrival("converge", "branch_b")
        r = record_branch_arrival("converge", "branch_c")
        assert r["data"]["ready"] is True
        assert r["data"]["waiting_on"] == []

        # get_active_plan surfaces converge as a ready gate, with no waiting join.
        plan = get_active_plan()
        assert plan["ok"] is True
        member = plan["active_plan"]["members"]["artifact-flow"]
        assert "converge" in member["ready_gates"]
        assert member["waiting_joins"] == []

        # Position did NOT auto-fire — still at converge, lead must advance.
        assert member["current_state"] == "converge"
        assert get_current_state()["data"]["current_state"] == "converge"

        # The lead explicitly advances; only then does the position move.
        adv = advance("done")
        assert adv["ok"] is True
        assert adv["data"]["current_state"] == "done"


# ---------------------------------------------------------------------------
# Join state survives a simulated restart via resume (C3, MR7)
# ---------------------------------------------------------------------------

class TestJoinSurvivesRestart:
    def test_required_and_received_survive_resume(self):
        init = _init_join_workflow()
        state_file = init["data"]["state_file"]

        record_branch_arrival("converge", "branch_a")
        record_branch_arrival("converge", "branch_b")

        # Simulate a restart: drop the in-process session, then resume.
        _reset_session()
        res = resume(state_file)
        assert res["ok"] is True

        status = view_join_status()["data"]["joins"][0]
        assert status["state"] == "converge"
        assert set(status["required"]) == {"branch_a", "branch_b", "branch_c"}
        assert set(status["received"]) == {"branch_a", "branch_b"}
        assert status["waiting_on"] == ["branch_c"]
        assert status["ready"] is False


# ---------------------------------------------------------------------------
# Rework back-edge clears received (reset-on-reentry) (KD3, C4, MR7)
# ---------------------------------------------------------------------------

class TestReworkResetsReceived:
    def test_back_edge_reentry_clears_received(self):
        _init_join_workflow()
        advance("fanout")
        advance("converge")

        # First pass: all branches arrive, gate is ready.
        record_branch_arrival("converge", "branch_a")
        record_branch_arrival("converge", "branch_b")
        record_branch_arrival("converge", "branch_c")
        assert view_join_status()["data"]["joins"][0]["ready"] is True

        # Rework: lead routes the back-edge converge -> fanout (a predecessor
        # that feeds converge). Re-entering fanout clears converge's received.
        rework = advance("fanout")
        assert rework["ok"] is True

        status = view_join_status()["data"]["joins"][0]
        assert status["received"] == [], (
            "stale received set must not re-surface a false-ready gate"
        )
        assert set(status["waiting_on"]) == {"branch_a", "branch_b", "branch_c"}
        assert status["ready"] is False

        # The new pass starts empty and re-accumulates independently.
        record_branch_arrival("converge", "branch_a")
        status2 = view_join_status()["data"]["joins"][0]
        assert status2["received"] == ["branch_a"]
        assert status2["ready"] is False

    def test_reset_to_predecessor_clears_received(self):
        """DEFECT #1 — reset_to() must clear the convergence state's received
        set on rework re-entry, else the prior pass's full set re-surfaces the
        gate as falsely ready (KD3)."""
        _init_join_workflow()
        advance("fanout")
        advance("converge")
        record_branch_arrival("converge", "branch_a")
        record_branch_arrival("converge", "branch_b")
        record_branch_arrival("converge", "branch_c")
        assert view_join_status()["data"]["joins"][0]["ready"] is True

        # Rework via reset_to back to a predecessor that feeds converge.
        r = reset_to("fanout", trigger="rework needed", context="branch failed")
        assert r["ok"] is True

        status = view_join_status()["data"]["joins"][0]
        assert status["received"] == [], (
            "reset_to rework re-entry must clear stale received set"
        )
        assert status["ready"] is False

    def test_reset_to_convergence_state_directly_clears_received(self):
        """DEFECT #1 — reset_to onto the convergence state itself also clears."""
        _init_join_workflow()
        advance("fanout")
        advance("converge")
        record_branch_arrival("converge", "branch_a")
        record_branch_arrival("converge", "branch_b")

        # reset_to fanout then back to converge — re-entry of converge clears.
        reset_to("fanout", trigger="rework", context="restart pass")
        r = reset_to("converge", trigger="re-enter", context="new pass")
        assert r["ok"] is True
        status = view_join_status()["data"]["joins"][0]
        assert status["received"] == []
        assert status["ready"] is False

    def test_override_transition_to_predecessor_clears_received(self):
        """DEFECT #1 (2nd pass) — override_transition is a 4th force-move entry
        point and must ALSO clear the convergence state's received set on rework
        re-entry. After a full join pass, an override back to a convergence
        predecessor left received pre-loaded → view_join_status falsely reports
        ready=True for the new pass (KD3 — accumulator is per-pass, not
        cumulative)."""
        _init_join_workflow()
        advance("fanout")
        advance("converge")
        record_branch_arrival("converge", "branch_a")
        record_branch_arrival("converge", "branch_b")
        record_branch_arrival("converge", "branch_c")
        assert view_join_status()["data"]["joins"][0]["ready"] is True

        # Rework via override_transition back to a predecessor that feeds converge.
        r = override_transition(
            "fanout",
            reason="force rework after a complete pass",
            skipped_alternatives=["reset_to"],
            risks="bypasses transition rules",
        )
        assert r["ok"] is True

        status = view_join_status()["data"]["joins"][0]
        assert status["received"] == [], (
            "override_transition rework re-entry must clear stale received set"
        )
        assert status["ready"] is False


# A workflow where the convergence state's predecessor is 2+ hops upstream of
# the convergence state, exercising full reverse-reachability (DEFECT #4).
# start -> stage1 -> stage2 -> converge ; back-edge converge -> stage1.
TWO_HOP_JOIN_YAML = """\
states:
  start:
    handler_type: self
    transitions:
      - stage1
    input: "Initial"
    output: "Ready"
  stage1:
    handler_type: self
    transitions:
      - stage2
    input: "Stage 1"
    output: "Stage 1 done"
  stage2:
    handler_type: self
    transitions:
      - converge
    input: "Stage 2"
    output: "Stage 2 done"
  converge:
    handler_type: self
    transitions:
      - done
      - stage1
    join_required:
      - branch_a
      - branch_b
    input: "Branch results"
    output: "Converged"
  done:
    handler_type: self
    transitions: []
    input: "Converged"
    output: "Final"
"""


def _init_two_hop_workflow():
    caps = ["self"]
    graph = parse_workflow_yaml(TWO_HOP_JOIN_YAML)
    assert not (isinstance(graph, dict) and "ok" in graph and not graph["ok"]), graph
    err = validate_graph(graph, caps)
    assert err is None, err
    return init_state(caps, graph)


class TestMultiHopReworkReset:
    def test_two_hop_back_edge_reentry_clears_received(self):
        """DEFECT #4 — a back-edge to a state 2+ hops upstream of the
        convergence state must still clear the convergence state's received set.
        One-hop successor check leaves it uncleared (KD3 — per-pass, not
        cumulative)."""
        _init_two_hop_workflow()
        advance("stage1")
        advance("stage2")
        advance("converge")
        record_branch_arrival("converge", "branch_a")
        record_branch_arrival("converge", "branch_b")
        assert view_join_status()["data"]["joins"][0]["ready"] is True

        # Back-edge converge -> stage1: stage1 is 2 hops upstream of converge.
        rework = advance("stage1")
        assert rework["ok"] is True

        status = view_join_status()["data"]["joins"][0]
        assert status["received"] == [], (
            "back-edge to a 2-hop-upstream predecessor must clear received"
        )
        assert set(status["waiting_on"]) == {"branch_a", "branch_b"}
        assert status["ready"] is False
