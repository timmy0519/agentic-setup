"""Phase 5 acceptance tests: Session management + hardening over MCP stdio transport."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers (reuse transport pattern from prior phases)
# ---------------------------------------------------------------------------

PROJECT_DIR = str(Path(__file__).resolve().parent.parent)

VALID_WORKFLOW = """\
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
    """Manages one MCP server subprocess per test."""

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
        assert self.proc.stdin is not None
        self.proc.stdin.write(payload.encode() + b"\n")
        self.proc.stdin.flush()

    def _recv(self) -> dict:
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        if not line:
            stderr = self.proc.stderr.read().decode() if self.proc.stderr else ""
            raise RuntimeError(f"Server closed stdout. stderr:\n{stderr}")
        return json.loads(line)

    def _handshake(self) -> None:
        self._req_id += 1
        init_req = _jsonrpc_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-harness", "version": "0.1"},
            },
            req_id=self._req_id,
        )
        self._send(init_req)
        resp = self._recv()
        assert resp.get("id") == self._req_id, f"Bad init response: {resp}"
        self._send(_jsonrpc_notification("notifications/initialized"))

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        self._req_id += 1
        req = _jsonrpc_request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            req_id=self._req_id,
        )
        self._send(req)
        resp = self._recv()
        assert resp.get("id") == self._req_id, f"Unexpected id: {resp}"
        return resp

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.terminate()
        self.proc.wait(timeout=5)

    def kill(self) -> None:
        """Hard-kill the server process (simulates crash)."""
        self.proc.kill()
        self.proc.wait(timeout=5)


def _extract_content(resp: dict) -> dict:
    """Pull parsed JSON from the MCP tool-call result envelope."""
    result = resp["result"]
    content_list = result.get("content", [])
    assert len(content_list) >= 1, f"No content in result: {result}"
    text = content_list[0]["text"]
    return json.loads(text)


@pytest.fixture()
def session(tmp_path: Path):
    """Yield a fresh MCPSession whose CWD is a temp dir."""
    s = MCPSession(cwd=tmp_path)
    yield s
    s.close()


def _init_workflow(session: MCPSession) -> dict:
    """Helper: init the standard 3-state workflow, assert success, return body."""
    resp = session.call_tool("init", {
        "capabilities": ["self"],
        "workflow_yaml": VALID_WORKFLOW,
    })
    body = _extract_content(resp)
    assert body["ok"] is True
    return body


# ---------------------------------------------------------------------------
# Test 1: Session file path isolation
# ---------------------------------------------------------------------------

class TestSessionFilePathIsolation:
    def test_two_inits_create_different_session_dirs(self, tmp_path: Path) -> None:
        """#1 — Two inits with different sessions write to different paths under .task-tool/<session-id>/."""
        # Session A
        s1 = MCPSession(cwd=tmp_path)
        resp1 = s1.call_tool("init", {
            "capabilities": ["self"],
            "workflow_yaml": VALID_WORKFLOW,
        })
        body1 = _extract_content(resp1)
        assert body1["ok"] is True
        state_file_1 = body1["data"]["state_file"]
        session_id_1 = body1["data"]["session_id"]

        # Session B — same workdir, different server process
        s2 = MCPSession(cwd=tmp_path)
        resp2 = s2.call_tool("init", {
            "capabilities": ["self"],
            "workflow_yaml": VALID_WORKFLOW,
        })
        body2 = _extract_content(resp2)
        assert body2["ok"] is True
        state_file_2 = body2["data"]["state_file"]
        session_id_2 = body2["data"]["session_id"]

        # Different session IDs
        assert session_id_1 != session_id_2

        # Different file paths
        assert state_file_1 != state_file_2

        # Both under .task-tool/
        assert "/.task-tool/" in state_file_1
        assert "/.task-tool/" in state_file_2

        # Both files exist
        assert Path(state_file_1).exists()
        assert Path(state_file_2).exists()

        # Session IDs appear in the paths
        assert session_id_1 in state_file_1
        assert session_id_2 in state_file_2

        s1.close()
        s2.close()


# ---------------------------------------------------------------------------
# Test 2: Resume from existing file
# ---------------------------------------------------------------------------

class TestResumeFromExistingFile:
    def test_resume_restores_position_and_history(self, tmp_path: Path) -> None:
        """#2 — Init with resume_from → position restored; history intact; can advance from persisted state."""
        # Phase 1: create session, advance, record output
        s1 = MCPSession(cwd=tmp_path)
        body1 = _init_workflow(s1)
        state_file = body1["data"]["state_file"]

        # Advance to middle
        resp = s1.call_tool("advance", {"target": "middle"})
        body = _extract_content(resp)
        assert body["ok"] is True

        # Record output at middle
        resp = s1.call_tool("record_output", {
            "state": "middle",
            "output_ref": "artifacts/design.md",
        })
        body = _extract_content(resp)
        assert body["ok"] is True

        # Kill server (simulate crash or normal shutdown)
        s1.close()

        # Phase 2: new server, resume from state_file
        s2 = MCPSession(cwd=tmp_path)
        resp = s2.call_tool("init", {"resume_from": state_file})
        body = _extract_content(resp)
        assert body["ok"] is True

        # Position should be at middle
        assert body["data"]["current_state"] == "middle"

        # History should be intact (init + advance + record_output + resume = 4)
        assert body["data"]["history_count"] >= 4

        # Can advance from middle to end
        resp = s2.call_tool("advance", {"target": "end"})
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "end"

        s2.close()

    def test_resume_entry_point_is_init_resume_from(self, tmp_path: Path) -> None:
        """#2b — Resume is via init(resume_from=...), not a standalone resume tool."""
        # Phase 1: create session
        s1 = MCPSession(cwd=tmp_path)
        body1 = _init_workflow(s1)
        state_file = body1["data"]["state_file"]

        # Advance to middle
        s1.call_tool("advance", {"target": "middle"})
        s1.close()

        # Phase 2: resume via init(resume_from=...)
        s2 = MCPSession(cwd=tmp_path)
        resp = s2.call_tool("init", {"resume_from": state_file})
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "middle"

        # Verify transitions are available from resumed state
        resp = s2.call_tool("view_legal_transitions")
        body = _extract_content(resp)
        assert "end" in body["data"]["transitions"]

        s2.close()


# ---------------------------------------------------------------------------
# Test 3: Resume is conscious decision (no automatic discovery)
# ---------------------------------------------------------------------------

class TestResumeIsConsciousDecision:
    def test_new_init_does_not_auto_discover_existing_sessions(self, tmp_path: Path) -> None:
        """#3 — A fresh init creates a new session, NOT resuming from any existing one."""
        # Session 1: create and advance
        s1 = MCPSession(cwd=tmp_path)
        body1 = _init_workflow(s1)
        state_file_1 = body1["data"]["state_file"]
        s1.call_tool("advance", {"target": "middle"})
        s1.close()

        # Session 2: fresh init (no resume_from) — should get a NEW session at start
        s2 = MCPSession(cwd=tmp_path)
        body2 = _init_workflow(s2)
        assert body2["data"]["current_state"] == "start"
        assert body2["data"]["state_file"] != state_file_1
        assert body2["data"]["session_id"] != body1["data"]["session_id"]
        s2.close()

    def test_init_without_resume_from_ignores_existing_files(self, tmp_path: Path) -> None:
        """#3b — Even with existing state files on disk, a normal init creates fresh state."""
        # Create a session to put files on disk
        s1 = MCPSession(cwd=tmp_path)
        body1 = _init_workflow(s1)
        s1.call_tool("advance", {"target": "middle"})
        s1.call_tool("advance", {"target": "end"})
        s1.close()

        # New server — fresh init
        s2 = MCPSession(cwd=tmp_path)
        body2 = _init_workflow(s2)
        # Must be at start, not at end
        assert body2["data"]["current_state"] == "start"
        s2.close()


# ---------------------------------------------------------------------------
# Test 4: Crash recovery (kill → restart → resume)
# ---------------------------------------------------------------------------

class TestCrashRecovery:
    def test_kill_server_then_resume(self, tmp_path: Path) -> None:
        """#4 — Kill server → restart → resume from file → state reconstructed."""
        # Phase 1: create session, do work
        s1 = MCPSession(cwd=tmp_path)
        body1 = _init_workflow(s1)
        state_file = body1["data"]["state_file"]

        # Advance and record
        s1.call_tool("advance", {"target": "middle"})
        s1.call_tool("record_output", {
            "state": "middle",
            "output_ref": "artifacts/result.md",
        })

        # HARD KILL (simulates crash)
        s1.kill()

        # Verify state file still exists on disk
        assert Path(state_file).exists()

        # Phase 2: new server, resume
        s2 = MCPSession(cwd=tmp_path)
        resp = s2.call_tool("init", {"resume_from": state_file})
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "middle"
        assert body["data"]["history_count"] >= 3  # init + advance + record_output

        # Can continue advancing
        resp = s2.call_tool("advance", {"target": "end"})
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "end"

        s2.close()

    def test_resume_preserves_outputs(self, tmp_path: Path) -> None:
        """#4b — After crash recovery, recorded outputs are still present in history."""
        s1 = MCPSession(cwd=tmp_path)
        body1 = _init_workflow(s1)
        state_file = body1["data"]["state_file"]

        s1.call_tool("advance", {"target": "middle"})
        s1.call_tool("record_output", {
            "state": "start",
            "output_ref": "artifacts/plan.md",
        })
        s1.call_tool("record_output", {
            "state": "middle",
            "output_ref": "artifacts/impl.md",
        })

        s1.kill()

        # Resume
        s2 = MCPSession(cwd=tmp_path)
        s2.call_tool("init", {"resume_from": state_file})

        # Check history has record_output entries
        resp = s2.call_tool("view_history")
        hist = _extract_content(resp)
        operations = [e["operation"] for e in hist["data"]["entries"]]
        assert operations.count("record_output") == 2

        s2.close()


# ---------------------------------------------------------------------------
# Test 5: Invalid resume file (corrupted JSON)
# ---------------------------------------------------------------------------

class TestInvalidResumeFile:
    def test_corrupted_json_returns_structured_error(self, tmp_path: Path) -> None:
        """#5 — Corrupted JSON returns structured error; does not create partial state."""
        # Write a corrupted file
        bad_file = tmp_path / ".task-tool" / "bad-session" / "workflow-state.json"
        bad_file.parent.mkdir(parents=True)
        bad_file.write_text("{not valid json???")

        s = MCPSession(cwd=tmp_path)
        resp = s.call_tool("init", {"resume_from": str(bad_file)})
        body = _extract_content(resp)

        assert body["ok"] is False
        assert "error" in body
        # Should be INVALID_STRUCTURE or similar
        assert body["error"]["code"] in ("INVALID_STRUCTURE", "INVALID_STATE_FILE")
        assert body["error"]["details"] != {}
        assert body["error"]["guidance"] != ""

        # No session should be active — a fresh init should work
        body2 = _init_workflow(s)
        assert body2["ok"] is True
        s.close()

    def test_nonexistent_file_returns_structured_error(self, tmp_path: Path) -> None:
        """#5b — Nonexistent file path returns structured error."""
        s = MCPSession(cwd=tmp_path)
        fake_path = str(tmp_path / "does-not-exist.json")
        resp = s.call_tool("init", {"resume_from": fake_path})
        body = _extract_content(resp)

        assert body["ok"] is False
        assert body["error"]["code"] in ("NO_WORKFLOW", "FILE_NOT_FOUND", "INVALID_STRUCTURE")
        assert body["error"]["details"] != {}
        assert body["error"]["guidance"] != ""

        s.close()

    def test_valid_json_but_wrong_structure_returns_error(self, tmp_path: Path) -> None:
        """#5c — Valid JSON but not a workflow state file returns structured error."""
        bad_file = tmp_path / ".task-tool" / "wrong-structure" / "workflow-state.json"
        bad_file.parent.mkdir(parents=True)
        bad_file.write_text(json.dumps({"foo": "bar", "not_a_workflow": True}))

        s = MCPSession(cwd=tmp_path)
        resp = s.call_tool("init", {"resume_from": str(bad_file)})
        body = _extract_content(resp)

        assert body["ok"] is False
        assert body["error"]["guidance"] != ""

        s.close()


# ---------------------------------------------------------------------------
# Test 6: All error codes return guidance
# ---------------------------------------------------------------------------

class TestErrorCodesReturnGuidance:
    """Trigger various error codes and verify each has details + guidance fields."""

    def test_no_workflow_error_has_guidance(self, tmp_path: Path) -> None:
        """NO_WORKFLOW — calling advance without init."""
        s = MCPSession(cwd=tmp_path)
        resp = s.call_tool("advance", {"target": "middle"})
        body = _extract_content(resp)
        assert body["ok"] is False
        assert "guidance" in body["error"]
        assert body["error"]["guidance"] != ""
        s.close()

    def test_already_initialized_error_has_guidance(self, tmp_path: Path) -> None:
        """ALREADY_INITIALIZED — calling init twice."""
        s = MCPSession(cwd=tmp_path)
        _init_workflow(s)
        resp = s.call_tool("init", {
            "capabilities": ["self"],
            "workflow_yaml": VALID_WORKFLOW,
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "ALREADY_INITIALIZED"
        assert "details" in body["error"]
        assert body["error"]["details"] != {}
        assert "guidance" in body["error"]
        assert body["error"]["guidance"] != ""
        s.close()

    def test_illegal_transition_error_has_guidance(self, tmp_path: Path) -> None:
        """ILLEGAL_TRANSITION — advance to non-adjacent state."""
        s = MCPSession(cwd=tmp_path)
        _init_workflow(s)
        resp = s.call_tool("advance", {"target": "end"})  # start -> end is illegal
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "ILLEGAL_TRANSITION"
        assert "guidance" in body["error"]
        assert body["error"]["guidance"] != ""
        s.close()

    def test_state_not_found_error_has_guidance(self, tmp_path: Path) -> None:
        """STATE_NOT_FOUND — reset_to nonexistent state."""
        s = MCPSession(cwd=tmp_path)
        _init_workflow(s)
        resp = s.call_tool("reset_to", {"state": "nonexistent", "trigger": "test", "context": "testing"})
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "STATE_NOT_FOUND"
        assert "guidance" in body["error"]
        assert body["error"]["guidance"] != ""
        s.close()

    def test_position_blocked_error_has_guidance(self, tmp_path: Path) -> None:
        """POSITION_BLOCKED — advance while blocked."""
        s = MCPSession(cwd=tmp_path)
        _init_workflow(s)
        s.call_tool("mark_blocked", {"blocker": "test block", "unblock_condition": "unblock", "impact": "blocked"})
        resp = s.call_tool("advance", {"target": "middle"})
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "POSITION_BLOCKED"
        assert "guidance" in body["error"]
        assert body["error"]["guidance"] != ""
        s.close()

    def test_reason_required_error_has_guidance(self, tmp_path: Path) -> None:
        """REASON_REQUIRED — mark_blocked with empty reason."""
        s = MCPSession(cwd=tmp_path)
        _init_workflow(s)
        resp = s.call_tool("mark_blocked", {"blocker": "", "unblock_condition": "", "impact": ""})
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        assert "guidance" in body["error"]
        assert body["error"]["guidance"] != ""
        s.close()

    def test_version_not_found_error_has_guidance(self, tmp_path: Path) -> None:
        """VERSION_NOT_FOUND — view_version for nonexistent version."""
        s = MCPSession(cwd=tmp_path)
        _init_workflow(s)
        resp = s.call_tool("view_workflow", {"version": 99})
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "VERSION_NOT_FOUND"
        assert "details" in body["error"]
        assert body["error"]["details"] != {}
        assert "guidance" in body["error"]
        assert body["error"]["guidance"] != ""
        s.close()

    def test_invalid_structure_error_has_guidance(self, tmp_path: Path) -> None:
        """INVALID_STRUCTURE — init with a zero-state workflow_yaml (still a real
        structural error; capabilities are no longer a refusal path)."""
        s = MCPSession(cwd=tmp_path)
        resp = s.call_tool("init", {"capabilities": ["self"], "workflow_yaml": "states: {}\n"})
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "INVALID_STRUCTURE"
        assert "guidance" in body["error"]
        assert body["error"]["guidance"] != ""
        s.close()

    def test_init_no_yaml_uses_default_presenting_aspect(self, tmp_path: Path) -> None:
        """Omitting workflow_yaml falls back to the general-report presenting aspect + nudge."""
        s = MCPSession(cwd=tmp_path)
        resp = s.call_tool("init", {"title": "bare init"})
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["presenting_aspect"] == "default-general-report"
        assert "/artifact-flow" in body["recommendation"]
        # the default skeleton carries a user-review gate state
        wf = _extract_content(s.call_tool("view_workflow", {}))
        assert "review" in wf["data"]["yaml"]
        assert wf["data"]["current_state"] == "build"
        s.close()

    def test_init_with_yaml_tagged_custom(self, tmp_path: Path) -> None:
        """Authoring a workflow_yaml tags the presenting aspect as custom (no nudge)."""
        s = MCPSession(cwd=tmp_path)
        resp = s.call_tool("init", {
            "capabilities": ["self"],
            "workflow_yaml": "states:\n  a:\n    handler_type: self\n    transitions: []\n",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["presenting_aspect"] == "custom"
        assert "recommendation" not in body
        s.close()


# ---------------------------------------------------------------------------
# Test 7: End-to-end lifecycle
# ---------------------------------------------------------------------------

class TestEndToEndLifecycle:
    def test_full_lifecycle(self, tmp_path: Path) -> None:
        """#7 — Define workflow → advance → record_output → update_workflow → override → mark_blocked → reset_to → view ops → verify complete history."""
        s = MCPSession(cwd=tmp_path)

        # 1. Init workflow
        body = _init_workflow(s)
        state_file = body["data"]["state_file"]
        assert body["data"]["current_state"] == "start"

        # 2. Advance: start → middle
        resp = s.call_tool("advance", {"target": "middle"})
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "middle"

        # 3. Record output at middle
        resp = s.call_tool("record_output", {
            "state": "middle",
            "output_ref": "artifacts/design.md",
        })
        body = _extract_content(resp)
        assert body["ok"] is True

        # 4. Update workflow (add review state after middle)
        updated_yaml = """\
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
      - review
    input: "Output from start"
    output: "Ready for review"
  review:
    handler_type: self
    transitions:
      - end
    input: "Output from middle"
    output: "Ready for end"
  end:
    handler_type: self
    transitions: []
    input: "Output from review"
    output: "Final result"
"""
        resp = s.call_tool("update_workflow", {
            "workflow_yaml": updated_yaml,
            "reason": "adding review step",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["new_version"] == 2

        # 5. Override transition: middle → end (skipping review)
        resp = s.call_tool("override_transition", {
            "target": "end",
            "reason": "hotfix — skip review",
            "skipped_alternatives": ["advance to review first"],
            "risks": "review step outputs not produced",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "end"

        # 6. Mark blocked at end
        resp = s.call_tool("mark_blocked", {"blocker": "deploy gate locked", "unblock_condition": "gate unlocked", "impact": "deploy blocked"})
        body = _extract_content(resp)
        assert body["ok"] is True

        # 7. Reset to start
        resp = s.call_tool("reset_to", {
            "state": "start",
            "trigger": "gate unlocked",
            "context": "restarting after gate unlocked",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "start"
        assert body["data"]["blocked_cleared"] is True

        # 8. View current state
        resp = s.call_tool("view_current_state")
        body = _extract_content(resp)
        assert body["data"]["current_state"] == "start"

        # 9. View legal transitions
        resp = s.call_tool("view_legal_transitions")
        body = _extract_content(resp)
        assert "middle" in body["data"]["transitions"]

        # 10. View workflow
        resp = s.call_tool("view_workflow")
        body = _extract_content(resp)
        assert body["data"]["version"] == 2
        assert "review" in body["data"]["yaml"]

        # 11. View version 1
        resp = s.call_tool("view_workflow", {"version": 1})
        body = _extract_content(resp)
        assert body["ok"] is True
        assert "review" not in body["data"]["version"]["yaml"]

        # 12. View full history — verify all operations present
        resp = s.call_tool("view_history")
        hist = _extract_content(resp)
        operations = [e["operation"] for e in hist["data"]["entries"]]

        assert "init" in operations
        assert "advance" in operations
        assert "record_output" in operations
        assert "update_workflow" in operations
        assert "override_transition" in operations
        assert "mark_blocked" in operations
        assert "reset_to" in operations

        # Verify order
        expected_ops = [
            "init",
            "advance",
            "record_output",
            "update_workflow",
            "override_transition",
            "mark_blocked",
            "reset_to",
        ]
        assert operations == expected_ops
        assert hist["data"]["count"] == 7

        s.close()
