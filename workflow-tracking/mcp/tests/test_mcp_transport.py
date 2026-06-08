"""Phase 1 acceptance tests over MCP stdio transport (JSON-RPC 2.0)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
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
        import os
        import sys
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

    # -- low-level I/O ------------------------------------------------------

    def _send(self, payload: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(payload.encode() + b"\n")
        self.proc.stdin.flush()

    def _recv(self) -> dict:
        """Read one JSON-RPC response line from stdout."""
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        if not line:
            stderr = self.proc.stderr.read().decode() if self.proc.stderr else ""
            raise RuntimeError(f"Server closed stdout. stderr:\n{stderr}")
        return json.loads(line)

    # -- MCP handshake -------------------------------------------------------

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

        # Send initialized notification (no response expected)
        self._send(_jsonrpc_notification("notifications/initialized"))

    # -- tool calls ----------------------------------------------------------

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

    # -- cleanup -------------------------------------------------------------

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.terminate()
        self.proc.wait(timeout=5)


def _extract_content(resp: dict) -> dict:
    """Pull the parsed JSON from the MCP tool-call result envelope."""
    result = resp["result"]
    # FastMCP wraps tool output in content[].text
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInit:
    """Tests 1–5: init tool behavior."""

    def test_valid_3state_workflow(self, session: MCPSession) -> None:
        """#1 — Init with valid 3-state workflow returns ok + first state."""
        resp = session.call_tool("init", {
            "capabilities": ["self"],
            "workflow_yaml": VALID_WORKFLOW,
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "start"
        assert "session_id" in body["data"]

    def test_init_infers_missing_capabilities(self, session: MCPSession) -> None:
        """#2 — Permissive (NFR3/KD10): init unions the graph's handler types into
        caps instead of refusing, so a caps list omitting a used handler still
        succeeds. Capabilities are a descriptive record, not a gate."""
        resp = session.call_tool("init", {
            "capabilities": ["human"],  # workflow uses 'self' — previously a mismatch
            "workflow_yaml": VALID_WORKFLOW,
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "start"

    def test_malformed_yaml_dangling_transition(self, session: MCPSession) -> None:
        """#3 — Dangling transition target → INVALID_STRUCTURE."""
        yaml_str = """\
states:
  start:
    handler_type: self
    transitions:
      - nonexistent
    input: "Initial state"
    output: "Ready for next"
"""
        resp = session.call_tool("init", {
            "capabilities": ["self"],
            "workflow_yaml": yaml_str,
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "INVALID_STRUCTURE"

    def test_zero_states(self, session: MCPSession) -> None:
        """#4 — Init with zero states → INVALID_STRUCTURE."""
        yaml_str = "states: {}"
        resp = session.call_tool("init", {
            "capabilities": ["self"],
            "workflow_yaml": yaml_str,
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "INVALID_STRUCTURE"

    def test_init_called_twice(self, tmp_path: Path) -> None:
        """#5 — Init called twice → ALREADY_INITIALIZED."""
        s = MCPSession(cwd=tmp_path)
        try:
            # First init
            resp1 = s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
            })
            body1 = _extract_content(resp1)
            assert body1["ok"] is True

            # Second init (same session)
            resp2 = s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
            })
            body2 = _extract_content(resp2)
            assert body2["ok"] is False
            assert body2["error"]["code"] == "ALREADY_INITIALIZED"
        finally:
            s.close()


class TestAdvance:
    """Tests 6–7: advance tool behavior."""

    def _init_workflow(self, session: MCPSession) -> None:
        resp = session.call_tool("init", {
            "capabilities": ["self"],
            "workflow_yaml": VALID_WORKFLOW,
        })
        body = _extract_content(resp)
        assert body["ok"] is True

    def test_advance_legal(self, session: MCPSession) -> None:
        """#6 — Advance to legal target succeeds."""
        self._init_workflow(session)
        resp = session.call_tool("advance", {"target": "middle"})
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "middle"
        assert body["data"]["previous_state"] == "start"

    def test_advance_illegal(self, session: MCPSession) -> None:
        """#7 — Advance to non-legal target → ILLEGAL_TRANSITION."""
        self._init_workflow(session)
        resp = session.call_tool("advance", {"target": "end"})  # start → end not legal
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "ILLEGAL_TRANSITION"


class TestViews:
    """Tests 8–9: view tools."""

    def _init_workflow(self, session: MCPSession) -> None:
        resp = session.call_tool("init", {
            "capabilities": ["self"],
            "workflow_yaml": VALID_WORKFLOW,
        })
        body = _extract_content(resp)
        assert body["ok"] is True

    def test_view_legal_transitions(self, session: MCPSession) -> None:
        """#8 — view_legal_transitions returns correct list."""
        self._init_workflow(session)
        resp = session.call_tool("view_legal_transitions")
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "start"
        assert body["data"]["transitions"] == ["middle"]

    def test_view_current_state(self, session: MCPSession) -> None:
        """#9 — view_current_state returns current state."""
        self._init_workflow(session)
        resp = session.call_tool("view_current_state")
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "start"


class TestE2EWalk:
    """Test 10: walk a full 3-state linear workflow."""

    def test_full_walk(self, tmp_path: Path) -> None:
        """#10 — Walk start→middle→end; final state has empty transitions."""
        s = MCPSession(cwd=tmp_path)
        try:
            # Init
            resp = s.call_tool("init", {
                "capabilities": ["self"],
                "workflow_yaml": VALID_WORKFLOW,
            })
            body = _extract_content(resp)
            assert body["ok"] is True
            assert body["data"]["current_state"] == "start"
            assert body["data"]["transitions"] == ["middle"]

            # Advance start → middle
            resp = s.call_tool("advance", {"target": "middle"})
            body = _extract_content(resp)
            assert body["ok"] is True
            assert body["data"]["current_state"] == "middle"
            assert body["data"]["transitions"] == ["end"]

            # Advance middle → end
            resp = s.call_tool("advance", {"target": "end"})
            body = _extract_content(resp)
            assert body["ok"] is True
            assert body["data"]["current_state"] == "end"
            assert body["data"]["transitions"] == []

            # Verify final state via view tools
            resp = s.call_tool("view_current_state")
            body = _extract_content(resp)
            assert body["data"]["current_state"] == "end"

            resp = s.call_tool("view_legal_transitions")
            body = _extract_content(resp)
            assert body["data"]["transitions"] == []
        finally:
            s.close()
