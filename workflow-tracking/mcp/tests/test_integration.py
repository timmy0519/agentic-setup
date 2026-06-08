"""Integration tests — full lifecycle, session management, and resume."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from task_tool.yaml_parser import parse_workflow_yaml
from task_tool.validator import validate_graph
from task_tool.state import (
    init_state,
    advance,
    get_current_state,
    get_legal_transitions,
    record_output,
    view_history,
    mark_blocked,
    reset_to,
    override_transition,
    update_workflow,
    view_version,
    view_workflow,
    resume,
    _state_path,
    _reset_session,
)
from task_tool.errors import (
    ALREADY_INITIALIZED,
    INVALID_STRUCTURE,
    NO_WORKFLOW,
)


SPEC_WORKFLOW_YAML = """\
states:
  requirements:
    handler_type: self
    transitions:
      - design
    input: "Project scope and goals"
    output: "Requirements document"
  design:
    handler_type: self
    transitions:
      - requirements
      - implementation
    input: "Requirements document"
    output: "Design document"
  implementation:
    handler_type: subagent
    transitions:
      - review
    input: "Design document"
    output: "Implementation artifacts"
  review:
    handler_type: peer
    transitions:
      - implementation
      - done
    input: "Implementation artifacts"
    output: "Review feedback"
  done:
    handler_type: self
    transitions: []
    input: "Approved review"
    output: "Final deliverable"
"""


def _init_spec_workflow():
    graph = parse_workflow_yaml(SPEC_WORKFLOW_YAML)
    err = validate_graph(graph, ["self", "subagent", "peer"])
    assert err is None
    return init_state(["self", "subagent", "peer"], graph)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# Session-scoped file paths
# ---------------------------------------------------------------------------

class TestSessionFilePathIsolation:
    def test_init_creates_session_scoped_path(self):
        result = _init_spec_workflow()
        assert result["ok"] is True
        state_file = result["data"]["state_file"]
        assert ".task-tool/" in state_file
        assert "/workflow-state.json" in state_file
        path = Path(state_file)
        assert path.exists()

    def test_two_sessions_write_different_paths(self, tmp_path):
        r1 = _init_spec_workflow()
        path1 = r1["data"]["state_file"]

        _reset_session()

        r2 = _init_spec_workflow()
        path2 = r2["data"]["state_file"]

        assert path1 != path2
        assert Path(path1).exists()
        assert Path(path2).exists()

    def test_session_id_in_path(self):
        result = _init_spec_workflow()
        session_id = result["data"]["session_id"]
        state_file = result["data"]["state_file"]
        assert session_id in state_file


# ---------------------------------------------------------------------------
# Resume via init(resume_from=...)
# ---------------------------------------------------------------------------

class TestResumeFromFile:
    def test_resume_restores_position(self):
        r_init = _init_spec_workflow()
        advance("design")
        advance("implementation")
        state_file = r_init["data"]["state_file"]

        _reset_session()

        r_resume = resume(state_file)
        assert r_resume["ok"] is True
        assert r_resume["data"]["current_state"] == "implementation"
        assert r_resume["data"]["session_id"] == r_init["data"]["session_id"]

    def test_resume_history_intact(self):
        r_init = _init_spec_workflow()
        advance("design")
        record_output("design", "design.md")
        state_file = r_init["data"]["state_file"]

        _reset_session()
        resume(state_file)

        result = view_history()
        assert result["ok"] is True
        # init + advance + record_output + resume = 4 entries
        assert result["data"]["count"] == 4
        ops = [e["operation"] for e in result["data"]["entries"]]
        assert ops == ["init", "advance", "record_output", "resume"]

    def test_resume_allows_advance(self):
        r_init = _init_spec_workflow()
        advance("design")
        state_file = r_init["data"]["state_file"]

        _reset_session()
        resume(state_file)

        result = advance("implementation")
        assert result["ok"] is True
        assert result["data"]["current_state"] == "implementation"

    def test_resume_is_conscious_decision(self):
        _init_spec_workflow()
        _reset_session()

        result = resume("/nonexistent/path/workflow-state.json")
        assert result["ok"] is False
        assert result["error"]["code"] == NO_WORKFLOW

    def test_resume_while_session_active_rejected(self):
        r_init = _init_spec_workflow()
        state_file = r_init["data"]["state_file"]

        result = resume(state_file)
        assert result["ok"] is False
        assert result["error"]["code"] == ALREADY_INITIALIZED


# ---------------------------------------------------------------------------
# Crash recovery
# ---------------------------------------------------------------------------

class TestCrashRecovery:
    def test_state_reconstructed_from_json(self):
        r_init = _init_spec_workflow()
        advance("design")
        mark_blocked("waiting on stakeholder", "stakeholder responds", "design blocked")
        state_file = r_init["data"]["state_file"]

        _reset_session()

        r_resume = resume(state_file)
        assert r_resume["ok"] is True
        assert r_resume["data"]["current_state"] == "design"

        data = json.loads(Path(state_file).read_text())
        assert (
            data["workflows"]["artifact-flow"]["position"]["blocked"]["blocker"]
            == "waiting on stakeholder"
        )


class TestInvalidResumeFile:
    def test_corrupted_json_rejected(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{")

        result = resume(str(bad_file))
        assert result["ok"] is False
        assert result["error"]["code"] == INVALID_STRUCTURE
        assert "file_path" in result["error"]["details"]

    def test_missing_fields_rejected(self, tmp_path):
        bad_file = tmp_path / "incomplete.json"
        bad_file.write_text(json.dumps({"meta": {}}))

        result = resume(str(bad_file))
        assert result["ok"] is False
        assert result["error"]["code"] == INVALID_STRUCTURE


# ---------------------------------------------------------------------------
# Error guidance audit
# ---------------------------------------------------------------------------

class TestErrorGuidance:
    def _assert_error_has_guidance(self, result):
        assert result["ok"] is False
        err = result["error"]
        assert "code" in err
        assert "message" in err
        assert "guidance" in err
        assert len(err["guidance"]) > 0, f"Empty guidance for {err['code']}"

    def test_no_workflow_guidance(self):
        self._assert_error_has_guidance(advance("anywhere"))

    def test_already_initialized_guidance(self):
        _init_spec_workflow()
        graph = parse_workflow_yaml(SPEC_WORKFLOW_YAML)
        validate_graph(graph, ["self", "subagent", "peer"])
        self._assert_error_has_guidance(
            init_state(["self", "subagent", "peer"], graph)
        )

    def test_illegal_transition_guidance(self):
        _init_spec_workflow()
        self._assert_error_has_guidance(advance("done"))

    def test_position_blocked_guidance(self):
        _init_spec_workflow()
        mark_blocked("stuck", "get unstuck", "nothing moves")
        self._assert_error_has_guidance(advance("design"))

    def test_reason_required_guidance(self):
        _init_spec_workflow()
        self._assert_error_has_guidance(mark_blocked("", "", ""))

    def test_state_not_found_guidance(self):
        _init_spec_workflow()
        self._assert_error_has_guidance(reset_to("phantom", "test trigger", "test context"))

    def test_state_not_visited_guidance(self):
        _init_spec_workflow()
        self._assert_error_has_guidance(record_output("design", "x"))


# ---------------------------------------------------------------------------
# Full lifecycle: spec-authoring workflow
# ---------------------------------------------------------------------------

class TestFullLifecycle:
    def test_spec_authoring_workflow_end_to_end(self):
        # 1. Init
        r = _init_spec_workflow()
        assert r["ok"] is True
        assert r["data"]["current_state"] == "requirements"

        # 2. Advance requirements → design
        r = advance("design")
        assert r["ok"] is True

        # 3. Record output for design
        r = record_output("design", "specs/design.md")
        assert r["ok"] is True

        # 4. Advance design → implementation
        r = advance("implementation")
        assert r["ok"] is True

        # 5. Advance implementation → review
        r = advance("review")
        assert r["ok"] is True

        # 6. Block at review
        r = mark_blocked("reviewer unavailable", "reviewer returns", "review delayed")
        assert r["ok"] is True

        # 7. Override: skip back to implementation
        r = override_transition(
            "implementation",
            "reviewer OOO, rework needed",
            ["review"],
            "skipping review cycle",
        )
        assert r["ok"] is True
        assert r["data"]["blocked_cleared"] is True

        # 8. Update workflow: add a testing state
        updated_yaml = """\
states:
  requirements:
    handler_type: self
    transitions:
      - design
    input: "Project scope and goals"
    output: "Requirements document"
  design:
    handler_type: self
    transitions:
      - requirements
      - implementation
    input: "Requirements document"
    output: "Design document"
  implementation:
    handler_type: subagent
    transitions:
      - testing
    input: "Design document"
    output: "Implementation artifacts"
  testing:
    handler_type: subagent
    transitions:
      - review
    input: "Implementation artifacts"
    output: "Test results"
  review:
    handler_type: peer
    transitions:
      - implementation
      - done
    input: "Test results"
    output: "Review feedback"
  done:
    handler_type: self
    transitions: []
    input: "Approved review"
    output: "Final deliverable"
"""
        r = update_workflow(updated_yaml, "add testing phase")
        assert r["ok"] is True
        assert "testing" in r["data"]["added_states"]

        # 9. Advance implementation → testing
        r = advance("testing")
        assert r["ok"] is True

        # 10. Reset back to design
        r = reset_to("design", "scope changed", "need to redesign")
        assert r["ok"] is True

        # 11. View operations
        r = view_workflow()
        assert r["ok"] is True
        assert "testing" in r["data"]["yaml"]
        assert "mermaid" in r["data"]

        r = view_version(1)
        assert r["ok"] is True

        r = get_current_state()
        assert r["data"]["current_state"] == "design"

        r = get_legal_transitions()
        assert "requirements" in r["data"]["transitions"]
        assert "implementation" in r["data"]["transitions"]

        # 12. Verify complete history
        r = view_history()
        assert r["ok"] is True
        ops = [e["operation"] for e in r["data"]["entries"]]
        assert ops == [
            "init",
            "advance",
            "record_output",
            "advance",
            "advance",
            "mark_blocked",
            "override_transition",
            "update_workflow",
            "advance",
            "reset_to",
        ]

        # Verify JSON file state
        data = json.loads(_state_path().read_text())
        member = data["workflows"]["artifact-flow"]
        assert member["position"]["current_state"] == "design"
        assert member["workflow"]["version"] == 2
        assert len(data["versions"]) == 1
        assert len(data["history"]) == 10


class TestResumeInLifecycle:
    def test_resume_continues_lifecycle(self):
        r = _init_spec_workflow()
        state_file = r["data"]["state_file"]
        advance("design")
        record_output("design", "design.md")

        _reset_session()

        r = resume(state_file)
        assert r["ok"] is True
        assert r["data"]["current_state"] == "design"

        r = advance("implementation")
        assert r["ok"] is True
        assert r["data"]["current_state"] == "implementation"

        r = view_history()
        ops = [e["operation"] for e in r["data"]["entries"]]
        assert "resume" in ops


# ===========================================================================
# MCP transport integration tests
# ===========================================================================

PROJECT_DIR = str(Path(__file__).resolve().parent.parent)


def _jsonrpc_request(method: str, params: dict | None = None, req_id: int = 1) -> str:
    msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg)


def _jsonrpc_notification(method: str, params: dict | None = None) -> str:
    msg: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg)


class MCPSession:
    def __init__(self, cwd: Path) -> None:
        env = {
            **os.environ,
            "TASK_TOOL_WORKDIR": str(cwd),
            "PYTHONPATH": str(Path(PROJECT_DIR) / "src"),
        }
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "task_tool.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        self._req_id = 0
        self._handshake()

    def _send(self, payload: str) -> None:
        self.proc.stdin.write(payload.encode() + b"\n")
        self.proc.stdin.flush()

    def _recv(self) -> dict:
        line = self.proc.stdout.readline()
        if not line:
            stderr = self.proc.stderr.read().decode() if self.proc.stderr else ""
            raise RuntimeError(f"Server closed stdout. stderr:\n{stderr}")
        return json.loads(line)

    def _handshake(self) -> None:
        self._req_id += 1
        self._send(_jsonrpc_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-harness", "version": "0.1"},
            },
            req_id=self._req_id,
        ))
        resp = self._recv()
        assert resp.get("id") == self._req_id
        self._send(_jsonrpc_notification("notifications/initialized"))

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        self._req_id += 1
        self._send(_jsonrpc_request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            req_id=self._req_id,
        ))
        resp = self._recv()
        assert resp.get("id") == self._req_id
        return resp

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.terminate()
        self.proc.wait(timeout=5)


def _extract(resp: dict) -> dict:
    content = resp["result"]["content"]
    assert len(content) >= 1
    return json.loads(content[0]["text"])


SPEC_CAPS = ["self", "subagent", "peer"]


class TestMCPSessionIsolation:
    """Session-scoped paths verified over MCP transport."""

    def test_init_returns_state_file_path(self, tmp_path):
        s = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s.call_tool("init", {
                "capabilities": SPEC_CAPS,
                "workflow_yaml": SPEC_WORKFLOW_YAML,
            }))
            assert body["ok"] is True
            assert "state_file" in body["data"]
            assert body["data"]["session_id"] in body["data"]["state_file"]
        finally:
            s.close()

    def test_two_mcp_sessions_different_paths(self, tmp_path):
        """Two separate MCP server processes create different session dirs."""
        s1 = MCPSession(cwd=tmp_path)
        try:
            b1 = _extract(s1.call_tool("init", {
                "capabilities": SPEC_CAPS,
                "workflow_yaml": SPEC_WORKFLOW_YAML,
            }))
            path1 = b1["data"]["state_file"]
        finally:
            s1.close()

        s2 = MCPSession(cwd=tmp_path)
        try:
            b2 = _extract(s2.call_tool("init", {
                "capabilities": SPEC_CAPS,
                "workflow_yaml": SPEC_WORKFLOW_YAML,
            }))
            path2 = b2["data"]["state_file"]
        finally:
            s2.close()

        assert path1 != path2


class TestMCPResume:
    """Resume via init(resume_from=...) over MCP transport."""

    def test_resume_restores_and_continues(self, tmp_path):
        # Session 1: init + advance
        s1 = MCPSession(cwd=tmp_path)
        try:
            b = _extract(s1.call_tool("init", {
                "capabilities": SPEC_CAPS,
                "workflow_yaml": SPEC_WORKFLOW_YAML,
            }))
            state_file = b["data"]["state_file"]

            b = _extract(s1.call_tool("advance", {"target": "design"}))
            assert b["ok"] is True
        finally:
            s1.close()

        # Session 2: resume from file
        s2 = MCPSession(cwd=tmp_path)
        try:
            b = _extract(s2.call_tool("init", {
                "resume_from": state_file,
            }))
            assert b["ok"] is True
            assert b["data"]["current_state"] == "design"

            # Can continue advancing
            b = _extract(s2.call_tool("advance", {"target": "implementation"}))
            assert b["ok"] is True
            assert b["data"]["current_state"] == "implementation"
        finally:
            s2.close()

    def test_resume_corrupted_file_rejected(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{{{broken")

        s = MCPSession(cwd=tmp_path)
        try:
            b = _extract(s.call_tool("init", {"resume_from": str(bad_file)}))
            assert b["ok"] is False
            assert b["error"]["code"] == "INVALID_STRUCTURE"
        finally:
            s.close()


class TestMCPFullLifecycle:
    """End-to-end lifecycle over MCP transport with resume."""

    def test_lifecycle_with_crash_and_resume(self, tmp_path):
        # Phase 1: init, advance, record, block
        s1 = MCPSession(cwd=tmp_path)
        try:
            b = _extract(s1.call_tool("init", {
                "capabilities": ["self", "subagent", "peer"],
                "workflow_yaml": SPEC_WORKFLOW_YAML,
            }))
            state_file = b["data"]["state_file"]

            _extract(s1.call_tool("advance", {"target": "design"}))
            _extract(s1.call_tool("record_output", {
                "state": "design", "output_ref": "design.md",
            }))
            _extract(s1.call_tool("advance", {"target": "implementation"}))
            _extract(s1.call_tool("mark_blocked", {"blocker": "build failure", "unblock_condition": "fix build", "impact": "deploy blocked"}))
        finally:
            s1.close()

        # Simulate crash — new server session
        s2 = MCPSession(cwd=tmp_path)
        try:
            # Resume
            b = _extract(s2.call_tool("init", {"resume_from": state_file}))
            assert b["ok"] is True
            assert b["data"]["current_state"] == "implementation"

            # Recovery: reset, override, continue
            b = _extract(s2.call_tool("reset_to", {
                "state": "design", "trigger": "fix build", "context": "build issue resolved",
            }))
            assert b["ok"] is True
            assert b["data"]["blocked_cleared"] is True

            b = _extract(s2.call_tool("advance", {"target": "implementation"}))
            assert b["ok"] is True

            # Verify full history
            b = _extract(s2.call_tool("view_history"))
            ops = [e["operation"] for e in b["data"]["entries"]]
            assert ops == [
                "init", "advance", "record_output", "advance",
                "mark_blocked", "resume", "reset_to", "advance",
            ]

            # Verify workflow view
            b = _extract(s2.call_tool("view_workflow"))
            assert b["ok"] is True
            assert "mermaid" in b["data"]
        finally:
            s2.close()
