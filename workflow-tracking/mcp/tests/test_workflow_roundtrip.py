"""Round-trip safety for view_workflow -> update_workflow and version archival.

DEFECT #2 — _generate_yaml must emit gate, join_required, acs (not just the
legacy four keys), else a view_workflow -> update_workflow round-trip silently
strips the new schema and corrupts archived version snapshots (KD1/KD3/KD5).

DEFECT #3 — update_workflow must orphan-clean joins/gate_evidence/acs for
removed states, mirroring the existing orphaned_outputs cleanup.
"""

from __future__ import annotations

import pytest

from task_tool.yaml_parser import parse_workflow_yaml
from task_tool.validator import validate_graph
from task_tool.state import (
    init_state,
    advance,
    record_branch_arrival,
    record_review_evidence,
    update_workflow,
    view_workflow,
    _reset_session,
)


# A workflow exercising all three new schema fields: a gate state, a join
# (convergence) state, and a state carrying ACs.
RICH_YAML = """\
states:
  start:
    handler_type: self
    transitions:
      - fanout
    input: "Initial"
    output: "Ready"
  fanout:
    handler_type: self
    transitions:
      - converge
    input: "Dispatch"
    output: "Dispatched"
  converge:
    handler_type: self
    transitions:
      - review
    join_required:
      - branch_a
      - branch_b
    input: "Branch results"
    output: "Converged"
  review:
    handler_type: self
    gate: true
    acs:
      - id: ac1
        statement: "Output must pass adversarial review"
      - id: ac2
        statement: "No unresolved blockers"
    transitions:
      - done
    input: "Reviewed"
    output: "Approved"
  done:
    handler_type: self
    transitions: []
    input: "Approved"
    output: "Final"
"""


def _init_rich_workflow():
    caps = ["self"]
    graph = parse_workflow_yaml(RICH_YAML)
    assert not (isinstance(graph, dict) and "ok" in graph and not graph["ok"]), graph
    err = validate_graph(graph, caps)
    assert err is None, err
    return init_state(caps, graph)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


class TestGeneratedYamlPreservesNewSchema:
    def test_generated_yaml_includes_gate_join_acs(self):
        """DEFECT #2 — the YAML emitted by view_workflow must carry the new
        fields so it parses back to the same graph."""
        _init_rich_workflow()
        yaml_str = view_workflow()["data"]["yaml"]

        reparsed = parse_workflow_yaml(yaml_str)
        assert not (isinstance(reparsed, dict) and "ok" in reparsed and not reparsed["ok"]), reparsed

        assert reparsed["review"].gate is True
        assert reparsed["converge"].join_required == ["branch_a", "branch_b"]
        assert len(reparsed["review"].acs) == 2
        assert {ac["id"] for ac in reparsed["review"].acs} == {"ac1", "ac2"}

    def test_round_trip_view_then_update_preserves_schema(self):
        """DEFECT #2 — view_workflow -> update_workflow leaves the gate/join/acs
        schema unchanged (no silent strip)."""
        _init_rich_workflow()
        yaml_str = view_workflow()["data"]["yaml"]

        r = update_workflow(yaml_str, reason="round-trip re-apply")
        assert r["ok"] is True, r

        after = view_workflow()["data"]
        reparsed = parse_workflow_yaml(after["yaml"])
        assert reparsed["review"].gate is True
        assert reparsed["converge"].join_required == ["branch_a", "branch_b"]
        assert len(reparsed["review"].acs) == 2

    def test_defaults_omitted_for_cleanliness(self):
        """DEFECT #2 — default values (gate=False, acs=[], join_required=[]) are
        omitted from emitted YAML; only non-default values are preserved."""
        _init_rich_workflow()
        yaml_str = view_workflow()["data"]["yaml"]
        # The plain `start` state has no gate/acs/join — none should appear in
        # its emitted block. Cheap structural check: count occurrences.
        # gate appears once (review), join_required once (converge), acs once.
        assert yaml_str.count("gate:") == 1
        assert yaml_str.count("join_required:") == 1
        assert yaml_str.count("acs:") == 1


class TestUpdateWorkflowOrphanCleansNewStores:
    def test_removed_state_orphans_join_gate_acs(self):
        """DEFECT #3 — when update_workflow removes a state, its entries in
        position.joins, position.gate_evidence and position.acs must be popped,
        mirroring orphaned_outputs cleanup."""
        from task_tool.state import _load_state, _resolve_member

        _init_rich_workflow()
        advance("fanout")
        advance("converge")
        record_branch_arrival("converge", "branch_a")
        record_review_evidence(gate_state="review")
        advance("review")

        # Confirm the new stores hold entries for converge/review.
        wsf = _load_state()
        entry, _ = _resolve_member(wsf, "artifact-flow")
        assert "converge" in entry.position.joins
        assert "review" in entry.position.gate_evidence

        # New workflow that DROPS converge and review entirely.
        trimmed = """\
states:
  start:
    handler_type: self
    transitions:
      - done
    input: "Initial"
    output: "Ready"
  done:
    handler_type: self
    transitions: []
    input: "Done"
    output: "Final"
"""
        r = update_workflow(trimmed, reason="drop join+gate states",
                            reset_to_state="start")
        assert r["ok"] is True, r

        wsf2 = _load_state()
        entry2, _ = _resolve_member(wsf2, "artifact-flow")
        assert "converge" not in entry2.position.joins, (
            "removed convergence state must be orphan-cleaned from joins"
        )
        assert "review" not in entry2.position.gate_evidence, (
            "removed gate state must be orphan-cleaned from gate_evidence"
        )
        assert "review" not in entry2.position.acs
        assert "converge" not in entry2.position.acs
