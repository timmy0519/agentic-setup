"""Acceptance tests: Ticket metadata & discovery over MCP stdio transport."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers (reuse transport pattern from test_phase5_mcp.py)
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


import subprocess


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
        assert resp.get("id") == self._req_id, f"Bad init response: {resp}"
        self._send(_jsonrpc_notification("notifications/initialized"))

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        self._req_id += 1
        self._send(_jsonrpc_request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            req_id=self._req_id,
        ))
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


def _extract(resp: dict) -> dict:
    """Pull parsed JSON from the MCP tool-call result envelope."""
    result = resp["result"]
    content_list = result.get("content", [])
    assert len(content_list) >= 1, f"No content in result: {result}"
    text = content_list[0]["text"]
    return json.loads(text)


# ---------------------------------------------------------------------------
# Test 1: Init with title/description/assignee
# ---------------------------------------------------------------------------

class TestInitWithMetadata:
    def test_init_stores_all_metadata_and_status_active(self, tmp_path: Path) -> None:
        """#1 — init with title/description/assignee → meta contains all 3; status = active."""
        s = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
                "title": "Research MCP patterns",
                "description": "Survey how MCP servers handle sessions",
                "assignee": "research-mcp-lead",
            }))
            assert body["ok"] is True

            # Read state file and verify meta
            state_file = Path(body["data"]["state_file"])
            data = json.loads(state_file.read_text())
            meta = data["meta"]
            assert meta["title"] == "Research MCP patterns"
            assert meta["description"] == "Survey how MCP servers handle sessions"
            assert meta["assignee"] == "research-mcp-lead"
            assert meta["status"] == "active"
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Test 2: Advance with summary
# ---------------------------------------------------------------------------

class TestAdvanceWithSummary:
    def test_advance_stores_exec_summary_and_history(self, tmp_path: Path) -> None:
        """#2 — advance with summary → meta.exec_summary updated; history entry includes summary."""
        s = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
            }))
            state_file = Path(body["data"]["state_file"])

            body = _extract(s.call_tool("advance", {
                "target": "middle",
                "summary": "Completed requirements gathering.",
            }))
            assert body["ok"] is True

            data = json.loads(state_file.read_text())
            assert data["meta"]["exec_summary"] == "Completed requirements gathering."

            # History entry has summary
            advance_entry = data["history"][1]  # [0]=init, [1]=advance
            assert advance_entry["operation"] == "advance"
            assert advance_entry["params"]["summary"] == "Completed requirements gathering."
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Test 3: Exec summary reflects latest advance only
# ---------------------------------------------------------------------------

class TestExecSummaryOverwrite:
    def test_multiple_advances_exec_summary_is_last(self, tmp_path: Path) -> None:
        """#3 — after multiple advances, exec_summary = last summary (overwritten)."""
        s = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
            }))
            state_file = Path(body["data"]["state_file"])

            _extract(s.call_tool("advance", {
                "target": "middle",
                "summary": "First phase complete.",
            }))
            _extract(s.call_tool("advance", {
                "target": "end",
                "summary": "All phases done, ready for review.",
            }))

            data = json.loads(state_file.read_text())
            assert data["meta"]["exec_summary"] == "All phases done, ready for review."
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Test 4: Auto-status: active → blocked → active
# ---------------------------------------------------------------------------

class TestAutoStatusBlocked:
    def test_blocked_then_reset_restores_active(self, tmp_path: Path) -> None:
        """#4 — mark_blocked → status=blocked; reset_to → status=active."""
        s = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
            }))
            state_file = Path(body["data"]["state_file"])

            # Mark blocked
            body = _extract(s.call_tool("mark_blocked", {"blocker": "waiting on API", "unblock_condition": "API available", "impact": "work stalled"}))
            assert body["ok"] is True
            data = json.loads(state_file.read_text())
            assert data["meta"]["status"] == "blocked"

            # Reset to start → active
            body = _extract(s.call_tool("reset_to", {
                "state": "start",
                "trigger": "API available now",
                "context": "can resume work",
            }))
            assert body["ok"] is True
            data = json.loads(state_file.read_text())
            assert data["meta"]["status"] == "active"
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Test 5: Auto-status: active → done (terminal state)
# ---------------------------------------------------------------------------

class TestAutoStatusDone:
    def test_advance_to_terminal_sets_done(self, tmp_path: Path) -> None:
        """#5 — advance to terminal state → status=done."""
        s = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
            }))
            state_file = Path(body["data"]["state_file"])

            _extract(s.call_tool("advance", {"target": "middle"}))
            _extract(s.call_tool("advance", {"target": "end"}))

            data = json.loads(state_file.read_text())
            assert data["meta"]["status"] == "done"
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Test 6: update_meta changes fields selectively
# ---------------------------------------------------------------------------

class TestUpdateMetaSelective:
    def test_update_title_only_leaves_description_unchanged(self, tmp_path: Path) -> None:
        """#6 — update title only → description unchanged."""
        s = MCPSession(cwd=tmp_path)
        try:
            _extract(s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
                "title": "Original Title",
                "description": "Original Description",
                "assignee": "original-assignee",
            }))

            body = _extract(s.call_tool("update_meta", {"title": "New Title"}))
            assert body["ok"] is True
            assert body["data"]["updated"]["title"] == "New Title"

            # Verify description and assignee unchanged via list_sessions
            body = _extract(s.call_tool("list_sessions"))
            sessions = body["data"]["sessions"]
            assert len(sessions) >= 1
            this_session = sessions[0]
            assert this_session["title"] == "New Title"
            # Also verify by reading state file directly
        finally:
            s.close()

    def test_update_title_preserves_other_fields_via_file(self, tmp_path: Path) -> None:
        """#6b — update title only → description and assignee preserved in state file."""
        s = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
                "title": "Keep Title",
                "description": "Keep Description",
                "assignee": "keep-assignee",
            }))
            state_file = Path(body["data"]["state_file"])

            _extract(s.call_tool("update_meta", {"title": "Changed Title"}))

            data = json.loads(state_file.read_text())
            assert data["meta"]["title"] == "Changed Title"
            assert data["meta"]["description"] == "Keep Description"
            assert data["meta"]["assignee"] == "keep-assignee"
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Test 7: list_sessions finds multiple sessions
# ---------------------------------------------------------------------------

class TestListSessionsMultiple:
    def test_two_sessions_same_workdir(self, tmp_path: Path) -> None:
        """#7 — create 2 sessions (separate servers, same workdir), list_sessions returns both."""
        s1 = MCPSession(cwd=tmp_path)
        try:
            _extract(s1.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
                "title": "Session Alpha",
                "assignee": "alpha-lead",
            }))
        finally:
            s1.close()

        s2 = MCPSession(cwd=tmp_path)
        try:
            _extract(s2.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
                "title": "Session Beta",
                "assignee": "beta-lead",
            }))
        finally:
            s2.close()

        # Third server lists without its own init
        s3 = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s3.call_tool("list_sessions"))
            assert body["ok"] is True
            sessions = body["data"]["sessions"]
            assert len(sessions) == 2
            titles = {s["title"] for s in sessions}
            assert titles == {"Session Alpha", "Session Beta"}
        finally:
            s3.close()


# ---------------------------------------------------------------------------
# Test 8: list_sessions without active session
# ---------------------------------------------------------------------------

class TestListSessionsNoActiveSession:
    def test_fresh_server_sees_existing_files(self, tmp_path: Path) -> None:
        """#8 — fresh server calls list_sessions, sees existing session files."""
        # Create a session and close
        s1 = MCPSession(cwd=tmp_path)
        try:
            _extract(s1.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
                "title": "Existing Session",
            }))
        finally:
            s1.close()

        # Fresh server — no init, just list
        s2 = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s2.call_tool("list_sessions"))
            assert body["ok"] is True
            assert len(body["data"]["sessions"]) == 1
            assert body["data"]["sessions"][0]["title"] == "Existing Session"
        finally:
            s2.close()

    def test_empty_workdir_returns_empty_list(self, tmp_path: Path) -> None:
        """#8b — no sessions at all → empty list, no error."""
        s = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s.call_tool("list_sessions"))
            assert body["ok"] is True
            assert body["data"]["sessions"] == []
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Test 9: Full handoff scenario: init → advance → kill → list → resume → continue
# ---------------------------------------------------------------------------

class TestHandoffRecovery:
    def test_full_handoff_lifecycle(self, tmp_path: Path) -> None:
        """#9 — init → advance → kill → list → resume → continue advancing."""
        # Phase 1: init and advance
        s1 = MCPSession(cwd=tmp_path)
        body = _extract(s1.call_tool("init", {
            "capabilities": ["self"],
            "workflow_yaml": VALID_WORKFLOW,
            "title": "Handoff Test",
            "description": "Testing full recovery",
            "assignee": "handoff-lead",
        }))
        state_file = body["data"]["state_file"]

        _extract(s1.call_tool("advance", {
            "target": "middle",
            "summary": "Requirements done, moving to implementation.",
        }))

        # Kill server (simulate crash)
        s1.kill()

        # Phase 2: new server — list sessions to discover
        s2 = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s2.call_tool("list_sessions"))
            assert body["ok"] is True
            sessions = body["data"]["sessions"]
            assert len(sessions) == 1
            found = sessions[0]
            assert found["title"] == "Handoff Test"
            assert found["current_state"] == "middle"
            assert found["exec_summary"] == "Requirements done, moving to implementation."
            assert found["status"] == "active"
            found_state_file = found["state_file"]

            # Resume from the discovered state file
            body = _extract(s2.call_tool("init", {"resume_from": found_state_file}))
            assert body["ok"] is True
            assert body["data"]["current_state"] == "middle"

            # Continue advancing
            body = _extract(s2.call_tool("advance", {
                "target": "end",
                "summary": "Implementation complete.",
            }))
            assert body["ok"] is True
            assert body["data"]["current_state"] == "end"

            # Verify final state
            data = json.loads(Path(state_file).read_text())
            assert data["meta"]["status"] == "done"
            assert data["meta"]["exec_summary"] == "Implementation complete."
        finally:
            s2.close()


# ---------------------------------------------------------------------------
# Test 10: Summary >500 words → warning but succeeds
# ---------------------------------------------------------------------------

class TestLongSummaryWarning:
    def test_advance_long_summary_warns_but_stores(self, tmp_path: Path) -> None:
        """#10 — summary >500 words → response has warning field, summary still stored."""
        s = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
            }))
            state_file = Path(body["data"]["state_file"])

            long_summary = " ".join(["word"] * 501)
            body = _extract(s.call_tool("advance", {
                "target": "middle",
                "summary": long_summary,
            }))
            assert body["ok"] is True
            assert "warning" in body["data"]
            assert "500" in body["data"]["warning"]

            # Summary still stored despite warning
            data = json.loads(state_file.read_text())
            assert data["meta"]["exec_summary"] == long_summary
        finally:
            s.close()

    def test_update_meta_long_summary_warns_but_stores(self, tmp_path: Path) -> None:
        """#10b — update_meta with long exec_summary also warns but stores."""
        s = MCPSession(cwd=tmp_path)
        try:
            _extract(s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
            }))

            long_summary = " ".join(["word"] * 501)
            body = _extract(s.call_tool("update_meta", {
                "exec_summary": long_summary,
            }))
            assert body["ok"] is True
            assert "warning" in body["data"]
            assert "500" in body["data"]["warning"]
        finally:
            s.close()
