"""Structured parameters acceptance tests for mark_blocked and reset_to over MCP stdio transport."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers (reuse transport pattern from Phase 3)
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
# AC 1: mark_blocked with all 3 fields
# ---------------------------------------------------------------------------

class TestMarkBlockedAllFields:
    def test_blocked_dict_and_history(self, session: MCPSession) -> None:
        """mark_blocked with all 3 fields: position.blocked is a dict with blocker,
        unblock_condition, impact; history entry has all 3."""
        _init_workflow(session)

        resp = session.call_tool("mark_blocked", {
            "blocker": "Search worker unavailable",
            "unblock_condition": "Team-lead spawns a worker",
            "impact": "Cannot draft without source material",
        })
        body = _extract_content(resp)
        assert body["ok"] is True

        # position.blocked is a dict with all 3 fields
        blocked = body["data"]["blocked"]
        assert blocked["blocker"] == "Search worker unavailable"
        assert blocked["unblock_condition"] == "Team-lead spawns a worker"
        assert blocked["impact"] == "Cannot draft without source material"

        # History entry has all 3 structured fields
        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        blocked_entry = hist["data"]["entries"][-1]
        assert blocked_entry["operation"] == "mark_blocked"
        assert blocked_entry["params"]["blocker"] == "Search worker unavailable"
        assert blocked_entry["params"]["unblock_condition"] == "Team-lead spawns a worker"
        assert blocked_entry["params"]["impact"] == "Cannot draft without source material"


# ---------------------------------------------------------------------------
# AC 2: mark_blocked missing a field -> REASON_REQUIRED
# ---------------------------------------------------------------------------

class TestMarkBlockedMissingField:
    def test_missing_blocker(self, session: MCPSession) -> None:
        """mark_blocked with blocker missing returns REASON_REQUIRED listing blocker."""
        _init_workflow(session)

        resp = session.call_tool("mark_blocked", {
            "unblock_condition": "something happens",
            "impact": "stuff is delayed",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        assert "blocker" in body["error"]["details"]["missing_fields"]

    def test_missing_unblock_condition(self, session: MCPSession) -> None:
        """mark_blocked with unblock_condition missing returns REASON_REQUIRED."""
        _init_workflow(session)

        resp = session.call_tool("mark_blocked", {
            "blocker": "something broke",
            "impact": "stuff is delayed",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        assert "unblock_condition" in body["error"]["details"]["missing_fields"]

    def test_missing_impact(self, session: MCPSession) -> None:
        """mark_blocked with impact missing returns REASON_REQUIRED."""
        _init_workflow(session)

        resp = session.call_tool("mark_blocked", {
            "blocker": "something broke",
            "unblock_condition": "fix it",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        assert "impact" in body["error"]["details"]["missing_fields"]


# ---------------------------------------------------------------------------
# AC 3: mark_blocked with empty field -> REASON_REQUIRED
# ---------------------------------------------------------------------------

class TestMarkBlockedEmptyField:
    def test_empty_blocker(self, session: MCPSession) -> None:
        """mark_blocked with empty blocker returns REASON_REQUIRED."""
        _init_workflow(session)

        resp = session.call_tool("mark_blocked", {
            "blocker": "",
            "unblock_condition": "something happens",
            "impact": "stuff is delayed",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        assert "blocker" in body["error"]["details"]["missing_fields"]

    def test_whitespace_only_fields(self, session: MCPSession) -> None:
        """mark_blocked with whitespace-only fields returns REASON_REQUIRED."""
        _init_workflow(session)

        resp = session.call_tool("mark_blocked", {
            "blocker": "   ",
            "unblock_condition": "  \t  ",
            "impact": "   ",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        missing = body["error"]["details"]["missing_fields"]
        assert "blocker" in missing
        assert "unblock_condition" in missing
        assert "impact" in missing


# ---------------------------------------------------------------------------
# AC 4: Advance while blocked shows structured info
# ---------------------------------------------------------------------------

class TestAdvanceWhileBlockedStructured:
    def test_position_blocked_includes_structured_details(self, session: MCPSession) -> None:
        """advance while blocked returns POSITION_BLOCKED with blocker,
        unblock_condition, impact in error details."""
        _init_workflow(session)

        session.call_tool("mark_blocked", {
            "blocker": "Search worker unavailable",
            "unblock_condition": "Team-lead spawns a worker",
            "impact": "Cannot draft without source material",
        })

        resp = session.call_tool("advance", {"target": "middle"})
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "POSITION_BLOCKED"

        # Error details include the structured blocked info
        details = body["error"]["details"]
        assert details["blocked"]["blocker"] == "Search worker unavailable"
        assert details["blocked"]["unblock_condition"] == "Team-lead spawns a worker"
        assert details["blocked"]["impact"] == "Cannot draft without source material"

        # Error message also mentions the blocker
        assert "Search worker unavailable" in body["error"]["message"]


# ---------------------------------------------------------------------------
# AC 5: reset_to with trigger + context
# ---------------------------------------------------------------------------

class TestResetToStructured:
    def test_reset_with_trigger_and_context(self, session: MCPSession) -> None:
        """reset_to with trigger + context: history entry has both fields;
        position unblocked."""
        _init_workflow(session)

        # Block first, then reset to verify unblocking
        session.call_tool("mark_blocked", {
            "blocker": "waiting on data",
            "unblock_condition": "data arrives",
            "impact": "pipeline stalled",
        })

        resp = session.call_tool("reset_to", {
            "state": "start",
            "trigger": "Worker delivered results",
            "context": "3 sources on session patterns received",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "start"
        assert body["data"]["blocked_cleared"] is True

        # History entry has trigger and context
        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        reset_entry = hist["data"]["entries"][-1]
        assert reset_entry["operation"] == "reset_to"
        assert reset_entry["params"]["trigger"] == "Worker delivered results"
        assert reset_entry["params"]["context"] == "3 sources on session patterns received"


# ---------------------------------------------------------------------------
# AC 6: reset_to missing trigger -> REASON_REQUIRED
# ---------------------------------------------------------------------------

class TestResetToMissingTrigger:
    def test_missing_trigger(self, session: MCPSession) -> None:
        """reset_to without trigger returns REASON_REQUIRED."""
        _init_workflow(session)

        resp = session.call_tool("reset_to", {
            "state": "start",
            "context": "some context here",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        assert "trigger" in body["error"]["details"]["missing_fields"]

    def test_empty_trigger(self, session: MCPSession) -> None:
        """reset_to with empty trigger returns REASON_REQUIRED."""
        _init_workflow(session)

        resp = session.call_tool("reset_to", {
            "state": "start",
            "trigger": "",
            "context": "some context here",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        assert "trigger" in body["error"]["details"]["missing_fields"]


# ---------------------------------------------------------------------------
# AC 7: reset_to missing context -> REASON_REQUIRED
# ---------------------------------------------------------------------------

class TestResetToMissingContext:
    def test_missing_context(self, session: MCPSession) -> None:
        """reset_to without context returns REASON_REQUIRED."""
        _init_workflow(session)

        resp = session.call_tool("reset_to", {
            "state": "start",
            "trigger": "something changed",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        assert "context" in body["error"]["details"]["missing_fields"]

    def test_empty_context(self, session: MCPSession) -> None:
        """reset_to with empty context returns REASON_REQUIRED."""
        _init_workflow(session)

        resp = session.call_tool("reset_to", {
            "state": "start",
            "trigger": "something changed",
            "context": "",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        assert "context" in body["error"]["details"]["missing_fields"]


# ---------------------------------------------------------------------------
# AC 8: Full cycle - block (structured) -> advance rejected (struct) ->
#        reset (structured) -> advance succeeds
# ---------------------------------------------------------------------------

class TestFullStructuredCycle:
    def test_end_to_end_structured_fields(self, session: MCPSession) -> None:
        """Full cycle: block with structured fields -> advance rejected showing
        struct -> reset with structured fields -> advance succeeds."""
        _init_workflow(session)

        # Step 1: block with structured fields
        resp = session.call_tool("mark_blocked", {
            "blocker": "Search worker unavailable",
            "unblock_condition": "Team-lead spawns a worker",
            "impact": "Cannot draft without source material",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["blocked"]["blocker"] == "Search worker unavailable"

        # Step 2: advance rejected - error includes structured blocked info
        resp = session.call_tool("advance", {"target": "middle"})
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "POSITION_BLOCKED"
        assert body["error"]["details"]["blocked"]["blocker"] == "Search worker unavailable"
        assert body["error"]["details"]["blocked"]["unblock_condition"] == "Team-lead spawns a worker"
        assert body["error"]["details"]["blocked"]["impact"] == "Cannot draft without source material"

        # Step 3: reset with structured fields
        resp = session.call_tool("reset_to", {
            "state": "start",
            "trigger": "Worker delivered results",
            "context": "3 sources on session patterns received",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["blocked_cleared"] is True
        assert body["data"]["current_state"] == "start"

        # Step 4: advance succeeds
        resp = session.call_tool("advance", {"target": "middle"})
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "middle"

        # Verify full history shows structured fields throughout
        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        entries = hist["data"]["entries"]
        operations = [e["operation"] for e in entries]
        assert operations == ["init", "mark_blocked", "reset_to", "advance"]

        # mark_blocked entry has structured fields
        blocked_entry = entries[1]
        assert blocked_entry["params"]["blocker"] == "Search worker unavailable"
        assert blocked_entry["params"]["unblock_condition"] == "Team-lead spawns a worker"
        assert blocked_entry["params"]["impact"] == "Cannot draft without source material"

        # reset_to entry has structured fields
        reset_entry = entries[2]
        assert reset_entry["params"]["trigger"] == "Worker delivered results"
        assert reset_entry["params"]["context"] == "3 sources on session patterns received"
