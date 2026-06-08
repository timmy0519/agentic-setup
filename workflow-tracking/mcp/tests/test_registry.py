"""Registry tests — meta-keyed workflow members, isolation, migration, rollup.

Covers US4 / MR3 / MR4 (registry), KD1 (init bootstrap + migration + rollup),
KD2 / C2 (per-member isolation), KD3a / NFR1 (single-writer contract), and
KD6 (HOLD-not-CAUSE structural — no record_hold tool / Meta.holds field).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from task_tool import state as state_mod
from task_tool.state import (
    init_state,
    advance,
    register_workflow,
    get_current_state,
    list_sessions,
    resume,
    update_meta,
    view_history,
    _state_path,
    _reset_session,
    DEFAULT_META_KEY,
)
from task_tool.models import Meta, WorkflowStateFile
from task_tool.yaml_parser import parse_workflow_yaml
from task_tool.validator import validate_graph
from task_tool.errors import ILLEGAL_TRANSITION


# ---------------------------------------------------------------------------
# Workflow YAML fixtures — two structurally distinct member graphs.
# ---------------------------------------------------------------------------

ARTIFACT_FLOW_YAML = """\
states:
  draft:
    handler_type: self
    transitions:
      - review
    input: "Initial draft"
    output: "Ready for review"
  review:
    handler_type: self
    transitions:
      - publish
    input: "Draft to review"
    output: "Ready to publish"
  publish:
    handler_type: self
    transitions: []
    input: "Reviewed artifact"
    output: "Published"
"""

# A second member with DISJOINT state names from artifact-flow, so an
# attempt to target one member's state from the other is provably off-graph.
PIPELINE_YAML = """\
states:
  ingest:
    handler_type: self
    transitions:
      - transform
    input: "Raw input"
    output: "Ingested"
  transform:
    handler_type: self
    transitions: []
    input: "Ingested data"
    output: "Transformed"
"""


def _init_artifact_flow(capabilities: list[str] | None = None):
    """Parse, validate, init the default artifact-flow member."""
    caps = capabilities or ["self"]
    graph = parse_workflow_yaml(ARTIFACT_FLOW_YAML)
    assert not (isinstance(graph, dict) and "ok" in graph and not graph["ok"]), graph
    err = validate_graph(graph, caps)
    assert err is None, err
    return init_state(caps, graph)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# Default member + second member registration (US4, MR3, MR4)
# ---------------------------------------------------------------------------

class TestDefaultMember:
    def test_init_graph_becomes_artifact_flow(self):
        result = _init_artifact_flow()
        assert result["ok"] is True
        # init's supplied graph is registered under the default key (KD1).
        assert result["data"]["meta_key"] == DEFAULT_META_KEY
        assert result["data"]["current_state"] == "draft"

    def test_default_member_persisted_under_key(self):
        _init_artifact_flow()
        data = json.loads(_state_path().read_text())
        assert DEFAULT_META_KEY in data["workflows"]
        assert (
            data["workflows"][DEFAULT_META_KEY]["position"]["current_state"]
            == "draft"
        )


class TestSecondMember:
    def test_register_second_member(self):
        _init_artifact_flow()
        result = register_workflow("pipeline", PIPELINE_YAML)
        assert result["ok"] is True
        assert result["data"]["meta_key"] == "pipeline"
        assert result["data"]["current_state"] == "ingest"
        assert set(result["data"]["registered"]) == {DEFAULT_META_KEY, "pipeline"}

    def test_both_members_advance_in_one_session(self):
        _init_artifact_flow()
        register_workflow("pipeline", PIPELINE_YAML)

        # artifact-flow member advances on the default meta_key.
        af = advance("review")
        assert af["ok"] is True, af
        assert af["data"]["current_state"] == "review"

        # pipeline member advances independently on its own meta_key.
        pl = advance("transform", meta_key="pipeline")
        assert pl["ok"] is True, pl
        assert pl["data"]["current_state"] == "transform"

        # Each member tracks its own position — no cross-contamination.
        assert get_current_state()["data"]["current_state"] == "review"
        assert (
            get_current_state(meta_key="pipeline")["data"]["current_state"]
            == "transform"
        )


# ---------------------------------------------------------------------------
# Isolation — per-member validation (KD2, C2)
# ---------------------------------------------------------------------------

class TestMemberIsolation:
    def test_cannot_target_other_members_state(self):
        """A member's advance cannot target a state owned by another member."""
        _init_artifact_flow()
        register_workflow("pipeline", PIPELINE_YAML)

        # 'ingest'/'transform' belong to pipeline, not artifact-flow.
        # Advancing artifact-flow to a pipeline state must be ILLEGAL — the
        # target is off this member's graph (transitions resolve per-member).
        result = advance("transform")
        assert result["ok"] is False
        assert result["error"]["code"] == ILLEGAL_TRANSITION
        assert "transform" not in result["error"]["details"]["legal_transitions"]

        # Symmetric: pipeline cannot reach an artifact-flow state.
        result2 = advance("review", meta_key="pipeline")
        assert result2["ok"] is False
        assert result2["error"]["code"] == ILLEGAL_TRANSITION

    def test_isolation_holds_without_a_hold_store(self):
        """KD2/KD6: cross-member references are structurally impossible because
        each member's transition table only names its own states — no separate
        'hold' store mediates isolation."""
        _init_artifact_flow()
        register_workflow("pipeline", PIPELINE_YAML)
        data = json.loads(_state_path().read_text())

        af_states = set(data["workflows"][DEFAULT_META_KEY]["workflow"]["states"])
        pl_states = set(data["workflows"]["pipeline"]["workflow"]["states"])
        # State namespaces are disjoint per member.
        assert af_states.isdisjoint(pl_states)
        # Every transition target named by a member resolves within that member.
        for member in data["workflows"].values():
            states = member["workflow"]["states"]
            for sdef in states.values():
                for target in sdef["transitions"]:
                    assert target in states


# ---------------------------------------------------------------------------
# Legacy migration (KD1, MR4)
# ---------------------------------------------------------------------------

def _write_legacy_state_file(path: Path) -> dict:
    """Craft a schema_version 1 file with the singular workflow/position shape.

    Deliberately OMITS the new Position/StateDefinition fields (acs, joins,
    gate_evidence, gate, join_required) so we exercise load-default-empty.
    """
    legacy = {
        "meta": {
            "schema_version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "session_id": "legacy-session-0001",
            "capabilities": ["self"],
            "title": "legacy workflow",
            "assignee": "lead",
            "status": "active",
            "exec_summary": "mid-flight",
        },
        "workflow": {
            "version": 1,
            "states": {
                "draft": {
                    "handler_type": "self",
                    "transitions": ["review"],
                    "input": "x",
                    "output": "y",
                },
                "review": {
                    "handler_type": "self",
                    "transitions": [],
                    "input": "y",
                    "output": "z",
                },
            },
        },
        "position": {
            "current_state": "draft",
            "blocked": None,
            "outputs": {},
            "visited": ["draft"],
        },
        "history": [
            {
                "seq": 1,
                "timestamp": "2026-01-01T00:00:00Z",
                "operation": "init",
                "params": {"starting_state": "draft"},
            }
        ],
        "versions": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(legacy, indent=2))
    return legacy


class TestLegacyMigration:
    def test_from_dict_wraps_singular_into_artifact_flow(self, tmp_path):
        legacy_path = tmp_path / ".task-tool" / "legacy" / "workflow-state.json"
        _write_legacy_state_file(legacy_path)
        data = json.loads(legacy_path.read_text())

        wsf = WorkflowStateFile.from_dict(data)

        # The singular workflow is wrapped under the default key (KD1).
        assert set(wsf.workflows.keys()) == {DEFAULT_META_KEY}
        member = wsf.workflows[DEFAULT_META_KEY]
        assert member.position.current_state == "draft"

    def test_migration_bumps_schema_version_to_2(self, tmp_path):
        legacy_path = tmp_path / ".task-tool" / "legacy" / "workflow-state.json"
        _write_legacy_state_file(legacy_path)
        data = json.loads(legacy_path.read_text())

        wsf = WorkflowStateFile.from_dict(data)
        assert wsf.meta.schema_version == 2  # forward-only 1 -> 2

    def test_new_fields_load_default_empty(self, tmp_path):
        legacy_path = tmp_path / ".task-tool" / "legacy" / "workflow-state.json"
        _write_legacy_state_file(legacy_path)
        data = json.loads(legacy_path.read_text())

        wsf = WorkflowStateFile.from_dict(data)
        member = wsf.workflows[DEFAULT_META_KEY]

        # Position new fields default empty — no KeyError on legacy load.
        assert member.position.joins == {}
        assert member.position.gate_evidence == {}
        assert member.position.acs == {}

        # StateDefinition new fields default empty on every state.
        for sdef in member.workflow.states.values():
            assert sdef.gate is False
            assert sdef.acs == []
            assert sdef.join_required == []

    def test_legacy_resumes_unchanged(self, tmp_path):
        """A legacy file resumes via resume(path), position intact."""
        legacy_path = tmp_path / ".task-tool" / "legacy" / "workflow-state.json"
        _write_legacy_state_file(legacy_path)
        _reset_session()  # no active session before resume

        result = resume(str(legacy_path))
        assert result["ok"] is True, result
        assert result["data"]["meta_key"] == DEFAULT_META_KEY
        assert result["data"]["current_state"] == "draft"

        # Position survived the migration; advance still legal on the graph.
        adv = advance("review")
        assert adv["ok"] is True, adv
        assert adv["data"]["current_state"] == "review"


# ---------------------------------------------------------------------------
# list_sessions per-member status rollup (KD1, MR4)
# ---------------------------------------------------------------------------

class TestSessionRollup:
    def test_list_sessions_reports_members(self):
        _init_artifact_flow()
        register_workflow("pipeline", PIPELINE_YAML)

        result = list_sessions()
        assert result["ok"] is True
        sessions = result["data"]["sessions"]
        assert len(sessions) == 1
        member_keys = {m["meta_key"] for m in sessions[0]["members"]}
        assert member_keys == {DEFAULT_META_KEY, "pipeline"}

    def test_rollup_blocked_beats_active_beats_done(self):
        """Session status = blocked > active > done across members."""
        from task_tool.state import mark_blocked

        _init_artifact_flow()
        register_workflow("pipeline", PIPELINE_YAML)

        # pipeline -> transform (terminal, no transitions) => done for pipeline.
        advance("transform", meta_key="pipeline")
        # artifact-flow still active (draft has a transition). Rollup => active.
        s_active = list_sessions()["data"]["sessions"][0]
        assert s_active["status"] == "active"

        # Block artifact-flow => any blocked member wins => blocked.
        mark_blocked("waiting on input", "input arrives", "draft stalled")
        s_blocked = list_sessions()["data"]["sessions"][0]
        assert s_blocked["status"] == "blocked"

    def test_rollup_done_when_all_members_terminal(self):
        """All members at terminal states => session done."""
        _init_artifact_flow()
        register_workflow("pipeline", PIPELINE_YAML)

        advance("review")
        advance("publish")  # artifact-flow terminal
        advance("transform", meta_key="pipeline")  # pipeline terminal

        s = list_sessions()["data"]["sessions"][0]
        assert s["status"] == "done"


# ---------------------------------------------------------------------------
# Single-writer invariant — contract-level (KD3a, C2, NFR1)
# ---------------------------------------------------------------------------

class TestSingleWriterContract:
    def test_mutating_ops_are_lead_scoped_module_funcs(self):
        """Single-writer-per-session: all mutating ops are module-level funcs
        operating on ONE active session path latched by init/resume — there is
        no per-member writer handle, so writes are serialized through the lead.
        """
        # init/resume are the ONLY session-latching entry points.
        assert callable(init_state)
        assert callable(resume)
        # Mutating ops take meta_key but share the single _active_session_path —
        # they cannot be aimed at an arbitrary file by a non-lead writer.
        import inspect

        for fn in (advance, register_workflow):
            params = inspect.signature(fn).parameters
            assert "file_path" not in params  # no caller-supplied target file
        # The session path is process-global module state, not a per-call arg.
        assert hasattr(state_mod, "_active_session_path")

    def test_single_active_session_latch(self):
        """A second init while a session is active is rejected — one writer
        owns the session, preventing concurrent divergent writers."""
        _init_artifact_flow()
        graph = parse_workflow_yaml(PIPELINE_YAML)
        result = init_state(["self"], graph)
        assert result["ok"] is False  # ALREADY_INITIALIZED


# ---------------------------------------------------------------------------
# HOLD-not-CAUSE structural absence (KD2, KD6, C2, MR4)
# ---------------------------------------------------------------------------

class TestHoldNotCauseStructural:
    def test_no_record_hold_tool(self):
        """KD6 dropped: there is NO record_hold function in the state layer."""
        assert not hasattr(state_mod, "record_hold")

    def test_no_meta_holds_field(self):
        """Meta carries no `holds` field — isolation is structural, not stored."""
        meta = Meta(
            schema_version=2,
            created_at="2026-01-01T00:00:00Z",
            session_id="s",
            capabilities=["self"],
        )
        assert not hasattr(meta, "holds")
        assert "holds" not in meta.to_dict()

    def test_transition_table_cannot_reference_foreign_state(self):
        """A member's transitions only name its own states — there is no
        mechanism (hold store or otherwise) to reference another member's
        state, so isolation holds by construction."""
        _init_artifact_flow()
        register_workflow("pipeline", PIPELINE_YAML)
        data = json.loads(_state_path().read_text())

        all_state_names = {
            mk: set(member["workflow"]["states"])
            for mk, member in data["workflows"].items()
        }
        for mk, member in data["workflows"].items():
            own = all_state_names[mk]
            foreign = set().union(
                *(s for k, s in all_state_names.items() if k != mk)
            )
            for sdef in member["workflow"]["states"].values():
                for target in sdef["transitions"]:
                    assert target in own
                    assert target not in foreign


# ---------------------------------------------------------------------------
# Member-filtered history includes cross-cutting session-level ops (SCOPE #2)
# ---------------------------------------------------------------------------

class TestHistoryMemberFilterIncludesSessionOps:
    def test_update_meta_visible_under_member_filter(self):
        """update_meta writes a session-level history entry with no meta_key
        tag. A per-member view_history(meta_key=X) must still surface it —
        session-scoped ops are cross-cutting and must not silently drop out of
        the per-member audit trail (KD1)."""
        _init_artifact_flow()
        r = update_meta(title="new title")
        assert r["ok"] is True

        result = view_history(meta_key="artifact-flow")
        assert result["ok"] is True
        ops = [e["operation"] for e in result["data"]["entries"]]
        assert "update_meta" in ops, (
            "session-level update_meta must appear in the member-filtered view"
        )

    def test_member_filter_excludes_other_members_tagged_ops(self):
        """The session-op inclusion must not leak ANOTHER member's tagged
        entries: a filtered view shows this member's tagged ops + untagged
        session ops, never a foreign member's tagged ops."""
        _init_artifact_flow()
        register_workflow("pipeline", PIPELINE_YAML)
        advance("transform", meta_key="pipeline")
        update_meta(title="cross-cutting change")

        result = view_history(meta_key="artifact-flow")
        assert result["ok"] is True
        entries = result["data"]["entries"]
        # Foreign member's tagged advance must NOT appear.
        foreign = [
            e for e in entries
            if e["operation"] == "advance" and e["params"].get("meta_key") == "pipeline"
        ]
        assert foreign == []
        # But the untagged session-level update_meta DOES appear.
        assert any(e["operation"] == "update_meta" for e in entries)
