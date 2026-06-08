"""Phase 6 acceptance tests: Ticket-style metadata and discovery."""

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
    mark_blocked,
    reset_to,
    override_transition,
    update_meta,
    list_sessions,
    _state_path,
    _reset_session,
)


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


def _init(
    yaml_str: str = VALID_3STATE_YAML,
    caps: list[str] | None = None,
    title: str = "",
    description: str = "",
    assignee: str = "",
):
    caps = caps or ["self"]
    graph = parse_workflow_yaml(yaml_str)
    assert not (isinstance(graph, dict) and "ok" in graph and not graph["ok"]), graph
    err = validate_graph(graph, caps)
    assert err is None, err
    return init_state(caps, graph, title=title, description=description, assignee=assignee)


def _read_meta() -> dict:
    data = json.loads(_state_path().read_text())
    return data["meta"]


def _read_history() -> list[dict]:
    data = json.loads(_state_path().read_text())
    return data["history"]


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# Init metadata
# ---------------------------------------------------------------------------

class TestInitMetadata:
    def test_init_stores_title_description_assignee(self):
        result = _init(
            title="Research MCP patterns",
            description="Survey how MCP servers handle sessions",
            assignee="research-mcp-lead",
        )
        assert result["ok"] is True

        meta = _read_meta()
        assert meta["title"] == "Research MCP patterns"
        assert meta["description"] == "Survey how MCP servers handle sessions"
        assert meta["assignee"] == "research-mcp-lead"

    def test_init_defaults_to_empty_strings(self):
        result = _init()
        assert result["ok"] is True

        meta = _read_meta()
        assert meta["title"] == ""
        assert meta["description"] == ""
        assert meta["assignee"] == ""

    def test_init_sets_status_active(self):
        result = _init()
        assert result["ok"] is True

        meta = _read_meta()
        assert meta["status"] == "active"

    def test_init_sets_empty_exec_summary(self):
        result = _init()
        assert result["ok"] is True

        meta = _read_meta()
        assert meta["exec_summary"] == ""


# ---------------------------------------------------------------------------
# Auto-derived status
# ---------------------------------------------------------------------------

class TestAutoStatus:
    def test_status_active_after_init(self):
        _init()
        assert _read_meta()["status"] == "active"

    def test_status_blocked_after_mark_blocked(self):
        _init()
        mark_blocked("waiting on API", "API available", "work stalled")
        assert _read_meta()["status"] == "blocked"

    def test_status_active_after_reset_to(self):
        _init()
        mark_blocked("stuck", "get unstuck", "nothing moves")
        reset_to("start", "cleared", "issue resolved")
        assert _read_meta()["status"] == "active"

    def test_status_done_at_terminal_state(self):
        _init()
        advance("middle")
        advance("end")
        assert _read_meta()["status"] == "done"

    def test_status_active_after_advance_to_non_terminal(self):
        _init()
        advance("middle")
        assert _read_meta()["status"] == "active"

    def test_status_done_after_override_to_terminal(self):
        _init()
        override_transition("end", "skip ahead", ["middle"], "no middle outputs")
        assert _read_meta()["status"] == "done"

    def test_status_active_after_override_to_non_terminal(self):
        _init()
        advance("middle")
        override_transition("start", "redo", ["end"], "restarting")
        assert _read_meta()["status"] == "active"


# ---------------------------------------------------------------------------
# Advance with summary
# ---------------------------------------------------------------------------

class TestAdvanceSummary:
    def test_advance_stores_exec_summary(self):
        _init()
        advance("middle", summary="Completed requirements gathering phase.")
        meta = _read_meta()
        assert meta["exec_summary"] == "Completed requirements gathering phase."

    def test_advance_overwrites_exec_summary(self):
        _init()
        advance("middle", summary="First summary.")
        advance("end", summary="Second summary.")
        meta = _read_meta()
        assert meta["exec_summary"] == "Second summary."

    def test_advance_without_summary_leaves_exec_summary_unchanged(self):
        _init()
        advance("middle", summary="Initial summary.")
        advance("end")  # No summary
        meta = _read_meta()
        assert meta["exec_summary"] == "Initial summary."

    def test_advance_summary_in_history(self):
        _init()
        advance("middle", summary="Did the thing.")
        history = _read_history()
        advance_entry = history[1]
        assert advance_entry["operation"] == "advance"
        assert advance_entry["params"]["summary"] == "Did the thing."

    def test_advance_long_summary_warns(self):
        _init()
        long_summary = " ".join(["word"] * 501)
        result = advance("middle", summary=long_summary)
        assert result["ok"] is True
        assert "warning" in result["data"]
        assert "500" in result["data"]["warning"]
        # Still stores the summary despite warning
        assert _read_meta()["exec_summary"] == long_summary

    def test_advance_short_summary_no_warning(self):
        _init()
        result = advance("middle", summary="Short and sweet.")
        assert result["ok"] is True
        assert "warning" not in result["data"]

    def test_advance_no_summary_no_summary_in_history(self):
        _init()
        advance("middle")
        history = _read_history()
        advance_entry = history[1]
        assert "summary" not in advance_entry["params"]


# ---------------------------------------------------------------------------
# update_meta
# ---------------------------------------------------------------------------

class TestUpdateMeta:
    def test_update_title(self):
        _init(title="Old Title")
        result = update_meta(title="New Title")
        assert result["ok"] is True
        assert result["data"]["updated"]["title"] == "New Title"
        assert _read_meta()["title"] == "New Title"

    def test_update_description(self):
        _init(description="Old desc")
        result = update_meta(description="New desc")
        assert result["ok"] is True
        assert _read_meta()["description"] == "New desc"

    def test_update_exec_summary(self):
        _init()
        result = update_meta(exec_summary="Manual summary update")
        assert result["ok"] is True
        assert _read_meta()["exec_summary"] == "Manual summary update"

    def test_update_multiple_fields(self):
        _init()
        result = update_meta(title="T", description="D", exec_summary="S")
        assert result["ok"] is True
        meta = _read_meta()
        assert meta["title"] == "T"
        assert meta["description"] == "D"
        assert meta["exec_summary"] == "S"

    def test_update_leaves_unspecified_fields_unchanged(self):
        _init(title="Keep This", description="Keep That", assignee="keep-me")
        update_meta(title="Changed")
        meta = _read_meta()
        assert meta["title"] == "Changed"
        assert meta["description"] == "Keep That"
        assert meta["assignee"] == "keep-me"

    def test_update_no_fields_returns_success(self):
        _init()
        result = update_meta()
        assert result["ok"] is True
        assert result["data"]["updated"] == {}

    def test_update_meta_appends_history(self):
        _init()
        update_meta(title="Updated")
        history = _read_history()
        last = history[-1]
        assert last["operation"] == "update_meta"
        assert last["params"]["updated_fields"]["title"] == "Updated"

    def test_update_meta_no_workflow_returns_error(self):
        result = update_meta(title="Nope")
        assert result["ok"] is False
        assert result["error"]["code"] == "NO_WORKFLOW"

    def test_update_meta_long_exec_summary_warns(self):
        _init()
        long_summary = " ".join(["word"] * 501)
        result = update_meta(exec_summary=long_summary)
        assert result["ok"] is True
        assert "warning" in result["data"]
        assert "500" in result["data"]["warning"]
        assert _read_meta()["exec_summary"] == long_summary

    def test_update_meta_short_exec_summary_no_warning(self):
        _init()
        result = update_meta(exec_summary="Brief update.")
        assert result["ok"] is True
        assert "warning" not in result["data"]


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------

class TestListSessions:
    def test_list_sessions_empty(self):
        result = list_sessions()
        assert result["ok"] is True
        assert result["data"]["sessions"] == []

    def test_list_sessions_finds_one(self):
        _init(title="My Workflow", assignee="test-lead")
        advance("middle", summary="Phase 1 done.")
        _reset_session()

        result = list_sessions()
        assert result["ok"] is True
        sessions = result["data"]["sessions"]
        assert len(sessions) == 1
        s = sessions[0]
        assert s["title"] == "My Workflow"
        assert s["assignee"] == "test-lead"
        assert s["status"] == "active"
        assert s["exec_summary"] == "Phase 1 done."
        assert s["current_state"] == "middle"
        assert "workflow-state.json" in s["state_file"]

    def test_list_sessions_finds_multiple(self):
        _init(title="Session A")
        _reset_session()

        _init(title="Session B")
        _reset_session()

        result = list_sessions()
        assert result["ok"] is True
        titles = {s["title"] for s in result["data"]["sessions"]}
        assert titles == {"Session A", "Session B"}

    def test_list_sessions_does_not_require_active_session(self):
        # No init at all — should work fine
        result = list_sessions()
        assert result["ok"] is True
        assert result["data"]["sessions"] == []

    def test_list_sessions_shows_correct_status(self):
        # Create a done session
        _init(title="Done Session")
        advance("middle")
        advance("end")
        _reset_session()

        # Create a blocked session
        _init(title="Blocked Session")
        mark_blocked("stuck", "get unstuck", "nothing moves")
        _reset_session()

        result = list_sessions()
        sessions = {s["title"]: s for s in result["data"]["sessions"]}
        assert sessions["Done Session"]["status"] == "done"
        assert sessions["Blocked Session"]["status"] == "blocked"


# ---------------------------------------------------------------------------
# MCP transport tests for new tools
# ---------------------------------------------------------------------------

PROJECT_DIR = str(Path(__file__).resolve().parent.parent)

VALID_WORKFLOW = VALID_3STATE_YAML


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


class TestMCPInitMetadata:
    def test_init_with_metadata(self, tmp_path: Path) -> None:
        s = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
                "title": "Test Workflow",
                "description": "Testing metadata",
                "assignee": "test-lead",
            }))
            assert body["ok"] is True

            # Read the state file to verify metadata
            state_file = Path(body["data"]["state_file"])
            data = json.loads(state_file.read_text())
            assert data["meta"]["title"] == "Test Workflow"
            assert data["meta"]["description"] == "Testing metadata"
            assert data["meta"]["assignee"] == "test-lead"
            assert data["meta"]["status"] == "active"
        finally:
            s.close()


class TestMCPAdvanceSummary:
    def test_advance_with_summary(self, tmp_path: Path) -> None:
        s = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
            }))
            state_file = Path(body["data"]["state_file"])

            body = _extract(s.call_tool("advance", {
                "target": "middle",
                "summary": "Finished start phase.",
            }))
            assert body["ok"] is True

            data = json.loads(state_file.read_text())
            assert data["meta"]["exec_summary"] == "Finished start phase."

            # History entry has summary
            advance_entry = data["history"][1]
            assert advance_entry["params"]["summary"] == "Finished start phase."
        finally:
            s.close()


class TestMCPUpdateMeta:
    def test_update_meta_over_mcp(self, tmp_path: Path) -> None:
        s = MCPSession(cwd=tmp_path)
        try:
            _extract(s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
                "title": "Original",
            }))

            body = _extract(s.call_tool("update_meta", {
                "title": "Updated Title",
                "exec_summary": "New summary",
            }))
            assert body["ok"] is True
            assert body["data"]["updated"]["title"] == "Updated Title"
            assert body["data"]["updated"]["exec_summary"] == "New summary"
        finally:
            s.close()


class TestMCPListSessions:
    def test_list_sessions_over_mcp(self, tmp_path: Path) -> None:
        # Create two sessions via two server processes
        s1 = MCPSession(cwd=tmp_path)
        try:
            _extract(s1.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
                "title": "Session One",
                "assignee": "lead-1",
            }))
        finally:
            s1.close()

        s2 = MCPSession(cwd=tmp_path)
        try:
            _extract(s2.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
                "title": "Session Two",
                "assignee": "lead-2",
            }))
        finally:
            s2.close()

        # New session to list (no init needed)
        s3 = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s3.call_tool("list_sessions"))
            assert body["ok"] is True
            sessions = body["data"]["sessions"]
            assert len(sessions) == 2
            titles = {s["title"] for s in sessions}
            assert titles == {"Session One", "Session Two"}
        finally:
            s3.close()

    def test_list_sessions_empty_dir(self, tmp_path: Path) -> None:
        s = MCPSession(cwd=tmp_path)
        try:
            body = _extract(s.call_tool("list_sessions"))
            assert body["ok"] is True
            assert body["data"]["sessions"] == []
        finally:
            s.close()
