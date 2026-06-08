"""Tests for the soft-gate path (KD5, US6, MR6, C5).

A gate state never hard-refuses. Entering a ``gate: true`` state:
  - WITH ``has-review-subagent-checked`` evidence (keyed by the gate state's
    name) → advance proceeds.
  - WITHOUT evidence → advance returns a SOFT recommendation (typed success,
    not a refusal) routing the lead to ``advance_without_evidence``.

``advance_without_evidence(target, reason)`` performs the move but REQUIRES a
legal transition (rejects an off-graph target — distinct from
``override_transition``'s force-move) and records a retrievable reason in
history. The bar is uniform for every gate — no risk tiers / no branches.
"""

from __future__ import annotations

import pytest

from task_tool.yaml_parser import parse_workflow_yaml
from task_tool.validator import validate_graph
from task_tool.state import (
    init_state,
    advance,
    advance_without_evidence,
    record_review_evidence,
    view_history,
)
from task_tool.errors import ILLEGAL_TRANSITION, REASON_REQUIRED


# Two consecutive gate states so we can test the uniform bar applies to EVERY
# gate (no tier branches): start -> review (gate) -> ship (gate) -> done.
GATE_YAML = """\
states:
  start:
    handler_type: self
    transitions:
      - review
    input: "Initial state"
    output: "Ready for review"
  review:
    handler_type: self
    gate: true
    transitions:
      - ship
    input: "Draft"
    output: "Reviewed"
  ship:
    handler_type: self
    gate: true
    transitions:
      - done
    input: "Reviewed"
    output: "Shipped"
  done:
    handler_type: self
    transitions: []
    input: "Shipped"
    output: "Final"
"""


def _init_gate_workflow():
    caps = ["self"]
    graph = parse_workflow_yaml(GATE_YAML)
    assert not (isinstance(graph, dict) and "ok" in graph and not graph["ok"]), graph
    err = validate_graph(graph, caps)
    assert err is None, err
    return init_state(caps, graph)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# Evidence present → advance proceeds (US6, MR6, C5)
# ---------------------------------------------------------------------------

class TestGateWithEvidence:
    def test_advance_with_evidence_proceeds(self):
        _init_gate_workflow()
        # Record review evidence keyed by the GATE state name, then advance.
        ev = record_review_evidence(gate_state="review")
        assert ev["ok"] is True
        assert ev["data"]["gate_evidence"]["has-review-subagent-checked"] is True

        result = advance("review")
        assert result["ok"] is True
        # Not a soft-gate recommendation — a real move.
        assert "soft_gate" not in result["data"]
        assert result["data"]["current_state"] == "review"
        assert result["data"]["previous_state"] == "start"

    def test_uniform_bar_every_gate_no_tier_branches(self):
        """The SAME evidence bar applies to every gate — no tier branching.

        review and ship are both gates; each independently requires its own
        has-review-subagent-checked evidence keyed by its own state name.
        """
        _init_gate_workflow()

        # First gate: evidence then advance.
        record_review_evidence(gate_state="review")
        r1 = advance("review")
        assert r1["ok"] is True
        assert "soft_gate" not in r1["data"]

        # Second gate WITHOUT its own evidence → soft recommendation, because
        # the bar is uniform (evidence for "review" does not satisfy "ship").
        r2_soft = advance("ship")
        assert r2_soft["ok"] is True
        assert r2_soft["data"]["soft_gate"] is True
        assert r2_soft["data"]["advanced"] is False

        # Same uniform bar cleared the same way → advance proceeds.
        record_review_evidence(gate_state="ship")
        r2 = advance("ship")
        assert r2["ok"] is True
        assert "soft_gate" not in r2["data"]
        assert r2["data"]["current_state"] == "ship"

    def test_evidence_keyed_by_gate_state_name(self):
        """Evidence for the wrong gate does NOT unlock a different gate."""
        _init_gate_workflow()
        # Record evidence for "ship" (not yet reachable) — must not unlock
        # "review", since gate_evidence is keyed by the gate state's name.
        record_review_evidence(gate_state="ship")
        soft = advance("review")
        assert soft["ok"] is True
        assert soft["data"]["soft_gate"] is True


# ---------------------------------------------------------------------------
# No evidence → SOFT recommendation, never a refusal (KD5, MR6)
# ---------------------------------------------------------------------------

class TestSoftGateRecommendation:
    def test_advance_without_evidence_returns_soft_not_refusal(self):
        _init_gate_workflow()
        result = advance("review")
        # Typed SUCCESS, not an error/refusal.
        assert result["ok"] is True
        data = result["data"]
        assert data["soft_gate"] is True
        assert data["advanced"] is False
        # Did NOT move — still at start.
        assert data["current_state"] == "start"
        assert data["target"] == "review"
        # Carries actionable guidance pointing to advance_without_evidence.
        assert "advance_without_evidence" in data["recommendation"]

    def test_soft_gate_does_not_mutate_position(self):
        """A soft recommendation must not silently advance the position."""
        _init_gate_workflow()
        advance("review")  # soft recommendation
        # A second plain advance still sees us at start (no move happened).
        again = advance("review")
        assert again["ok"] is True
        assert again["data"]["soft_gate"] is True
        assert again["data"]["current_state"] == "start"


# ---------------------------------------------------------------------------
# advance_without_evidence — recorded soft-gate audit path (KD5, MR6)
# ---------------------------------------------------------------------------

class TestAdvanceWithoutEvidence:
    def test_proceeds_and_records_retrievable_reason(self):
        _init_gate_workflow()
        reason = "Reviewer unavailable; deadline-driven, accepting risk."
        result = advance_without_evidence("review", reason=reason)
        assert result["ok"] is True
        data = result["data"]
        assert data["current_state"] == "review"
        assert data["previous_state"] == "start"
        assert data["evidence_bypassed"] is True
        assert data["reason"] == reason

        # Reason is retrievable from the audit history.
        hist = view_history()
        assert hist["ok"] is True
        awe = [
            e for e in hist["data"]["entries"]
            if e["operation"] == "advance_without_evidence"
        ]
        assert len(awe) == 1
        assert awe[0]["params"]["reason"] == reason
        assert awe[0]["params"]["from"] == "start"
        assert awe[0]["params"]["to"] == "review"

    def test_rejects_off_graph_target_legal_transition_required(self):
        """Distinct from override_transition: an off-graph target is REJECTED.

        From 'start' the only legal transition is 'review'. Targeting 'ship'
        (a real state but NOT a legal transition) must be refused — a legal
        transition is required, unlike override_transition's force-move.
        """
        _init_gate_workflow()
        result = advance_without_evidence("ship", reason="trying to skip ahead")
        assert result["ok"] is False
        assert result["error"]["code"] == ILLEGAL_TRANSITION
        # Position unchanged — still at start.
        from task_tool.state import get_current_state
        assert get_current_state()["data"]["current_state"] == "start"

    def test_requires_non_empty_reason(self):
        _init_gate_workflow()
        result = advance_without_evidence("review", reason="   ")
        assert result["ok"] is False
        assert result["error"]["code"] == REASON_REQUIRED

    def test_gate_never_hard_refuses_end_to_end(self):
        """Whole-path proof: a gate never hard-blocks.

        Without evidence, advance gives a soft rec (success), and
        advance_without_evidence completes the move with an audited reason.
        The agent is never stuck.
        """
        _init_gate_workflow()
        soft = advance("review")
        assert soft["ok"] is True and soft["data"]["soft_gate"] is True

        moved = advance_without_evidence("review", reason="proceeding deliberately")
        assert moved["ok"] is True
        assert moved["data"]["current_state"] == "review"


# A workflow whose start state transitions to a PLAIN (non-gate) state, so we
# can exercise the non-gate-target guard (DEFECT #5).
PLAIN_TARGET_YAML = """\
states:
  start:
    handler_type: self
    transitions:
      - plain
    input: "Initial"
    output: "Ready"
  plain:
    handler_type: self
    transitions:
      - done
    input: "Plain"
    output: "Plain done"
  done:
    handler_type: self
    transitions: []
    input: "Plain done"
    output: "Final"
"""


def _init_plain_target_workflow():
    caps = ["self"]
    graph = parse_workflow_yaml(PLAIN_TARGET_YAML)
    assert not (isinstance(graph, dict) and "ok" in graph and not graph["ok"]), graph
    err = validate_graph(graph, caps)
    assert err is None, err
    return init_state(caps, graph)


class TestAdvanceWithoutEvidenceRejectsNonGate:
    def test_non_gate_legal_target_succeeds_with_reason(self):
        """PERMISSIVE — task-tool RECORDS, it does not ENFORCE. `gate: true` is a
        convention marker, not a precondition. advance_without_evidence SUCCEEDS
        on a plain (non-gate) LEGAL target as long as a non-empty reason is given;
        it still requires a legal transition + reason (those are KEPT)."""
        from task_tool.state import view_history, get_current_state

        _init_plain_target_workflow()
        result = advance_without_evidence("plain", reason="proceeding deliberately")
        assert result["ok"] is True, result
        assert result["data"]["current_state"] == "plain"
        assert result["data"]["reason"] == "proceeding deliberately"

        # The move IS recorded as an audited entry.
        assert get_current_state()["data"]["current_state"] == "plain"
        hist = view_history()
        awe = [
            e for e in hist["data"]["entries"]
            if e["operation"] == "advance_without_evidence"
        ]
        assert len(awe) == 1, "the deliberate move must be recorded for audit"

    def test_off_graph_target_still_rejected(self):
        """KEEP — a legal transition is still required: an off-graph target is
        rejected (use override_transition to force-move off-graph)."""
        _init_plain_target_workflow()
        # 'done' is not a legal transition from 'start' (only 'plain' is).
        result = advance_without_evidence("done", reason="skip ahead")
        assert result["ok"] is False
        assert result["error"]["code"] == "ILLEGAL_TRANSITION"

    def test_empty_reason_still_rejected(self):
        """KEEP — a non-empty reason is still required."""
        _init_plain_target_workflow()
        result = advance_without_evidence("plain", reason="   ")
        assert result["ok"] is False
        assert result["error"]["code"] == "REASON_REQUIRED"
