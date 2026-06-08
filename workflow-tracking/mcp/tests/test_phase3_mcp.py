"""Phase 3 acceptance tests: Recovery operations over MCP stdio transport."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers (reuse transport pattern from Phase 2)
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
# Test 1: mark_blocked with reason
# ---------------------------------------------------------------------------

class TestMarkBlockedWithReason:
    def test_mark_blocked_sets_blocked_and_history(self, session: MCPSession) -> None:
        """#1 — mark_blocked with structured fields sets position.blocked as dict; history entry with fields."""
        _init_workflow(session)

        resp = session.call_tool("mark_blocked", {
            "blocker": "dependency unavailable",
            "unblock_condition": "dependency deployed",
            "impact": "design work stalled",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["blocked"]["blocker"] == "dependency unavailable"
        assert body["data"]["blocked"]["unblock_condition"] == "dependency deployed"
        assert body["data"]["blocked"]["impact"] == "design work stalled"
        assert body["data"]["current_state"] == "start"

        # Verify history entry
        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        assert hist["data"]["count"] == 2  # init + mark_blocked

        entry = hist["data"]["entries"][1]
        assert entry["operation"] == "mark_blocked"
        assert entry["params"]["blocker"] == "dependency unavailable"
        assert entry["params"]["unblock_condition"] == "dependency deployed"
        assert entry["params"]["impact"] == "design work stalled"
        assert entry["params"]["state"] == "start"


# ---------------------------------------------------------------------------
# Test 2: mark_blocked without reason → REASON_REQUIRED
# ---------------------------------------------------------------------------

class TestMarkBlockedNoReason:
    def test_mark_blocked_empty_fields_returns_error(self, session: MCPSession) -> None:
        """#2 — mark_blocked with empty fields returns REASON_REQUIRED error."""
        _init_workflow(session)

        resp = session.call_tool("mark_blocked", {
            "blocker": "",
            "unblock_condition": "",
            "impact": "",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        assert "blocker" in body["error"]["details"]["missing_fields"]

    def test_mark_blocked_whitespace_fields_returns_error(self, session: MCPSession) -> None:
        """#2b — mark_blocked with whitespace-only fields returns REASON_REQUIRED."""
        _init_workflow(session)

        resp = session.call_tool("mark_blocked", {
            "blocker": "   ",
            "unblock_condition": "   ",
            "impact": "   ",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"


# ---------------------------------------------------------------------------
# Test 3: Advance while blocked → POSITION_BLOCKED
# ---------------------------------------------------------------------------

class TestAdvanceWhileBlocked:
    def test_advance_while_blocked_returns_error(self, session: MCPSession) -> None:
        """#3 — advance while blocked returns POSITION_BLOCKED with reason and recovery suggestion."""
        _init_workflow(session)
        session.call_tool("mark_blocked", {
            "blocker": "waiting on external API",
            "unblock_condition": "API comes back",
            "impact": "integration stalled",
        })

        resp = session.call_tool("advance", {"target": "middle"})
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "POSITION_BLOCKED"
        assert "waiting on external API" in body["error"]["message"]
        # Should suggest recovery options
        assert "reset_to" in body["error"]["guidance"] or "override" in body["error"]["guidance"]


# ---------------------------------------------------------------------------
# Test 4: reset_to valid state
# ---------------------------------------------------------------------------

class TestResetToValid:
    def test_reset_to_valid_state(self, session: MCPSession) -> None:
        """#4 — reset_to forces position, clears blocked, history type = 'reset_to'."""
        _init_workflow(session)
        session.call_tool("advance", {"target": "middle"})
        session.call_tool("mark_blocked", {
            "blocker": "stuck",
            "unblock_condition": "get unstuck",
            "impact": "nothing moves",
        })

        resp = session.call_tool("reset_to", {
            "state": "start",
            "trigger": "retrying from scratch",
            "context": "decided to start over",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "start"
        assert body["data"]["previous_state"] == "middle"
        assert body["data"]["blocked_cleared"] is True

        # Verify history entry
        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        entries = hist["data"]["entries"]
        reset_entry = entries[-1]
        assert reset_entry["operation"] == "reset_to"
        assert reset_entry["params"]["from"] == "middle"
        assert reset_entry["params"]["to"] == "start"
        assert reset_entry["params"]["trigger"] == "retrying from scratch"
        assert reset_entry["params"]["context"] == "decided to start over"

    def test_reset_to_clears_blocked_flag(self, session: MCPSession) -> None:
        """#4b — After reset_to, advance works again (blocked cleared)."""
        _init_workflow(session)
        session.call_tool("mark_blocked", {
            "blocker": "stuck",
            "unblock_condition": "get unstuck",
            "impact": "nothing moves",
        })

        # Reset
        session.call_tool("reset_to", {
            "state": "start",
            "trigger": "unblocked now",
            "context": "issue resolved",
        })

        # Advance should work
        resp = session.call_tool("advance", {"target": "middle"})
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "middle"


# ---------------------------------------------------------------------------
# Test 5: reset_to nonexistent state → STATE_NOT_FOUND
# ---------------------------------------------------------------------------

class TestResetToNonexistent:
    def test_reset_to_nonexistent_state_returns_error(self, session: MCPSession) -> None:
        """#5 — reset_to nonexistent state returns STATE_NOT_FOUND."""
        _init_workflow(session)

        resp = session.call_tool("reset_to", {
            "state": "nonexistent",
            "trigger": "testing invalid reset",
            "context": "verifying error handling",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "STATE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Test 6: override_transition with full params
# ---------------------------------------------------------------------------

class TestOverrideTransitionFull:
    def test_override_transition_with_all_params(self, session: MCPSession) -> None:
        """#6 — override_transition moves to target even if not legal; history includes reason, skipped, risks."""
        _init_workflow(session)

        # start → end is NOT a legal transition (start → middle is)
        resp = session.call_tool("override_transition", {
            "target": "end",
            "reason": "skipping middle for hotfix",
            "skipped_alternatives": ["advance to middle first"],
            "risks": "middle state outputs not produced",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "end"
        assert body["data"]["previous_state"] == "start"

        # Verify history entry contains all fields
        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        override_entry = hist["data"]["entries"][-1]
        assert override_entry["operation"] == "override_transition"
        assert override_entry["params"]["from"] == "start"
        assert override_entry["params"]["to"] == "end"
        assert override_entry["params"]["reason"] == "skipping middle for hotfix"
        assert override_entry["params"]["skipped_alternatives"] == ["advance to middle first"]
        assert override_entry["params"]["risks"] == "middle state outputs not produced"


# ---------------------------------------------------------------------------
# Test 7: override_transition missing required fields → REASON_REQUIRED
# ---------------------------------------------------------------------------

class TestOverrideTransitionMissing:
    def test_override_missing_reason(self, session: MCPSession) -> None:
        """#7a — override_transition with empty reason returns REASON_REQUIRED."""
        _init_workflow(session)

        resp = session.call_tool("override_transition", {
            "target": "end",
            "reason": "",
            "skipped_alternatives": ["alt"],
            "risks": "some risk",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        assert "reason" in body["error"]["details"]["missing_fields"]

    def test_override_missing_risks(self, session: MCPSession) -> None:
        """#7b — override_transition with empty risks returns REASON_REQUIRED."""
        _init_workflow(session)

        resp = session.call_tool("override_transition", {
            "target": "end",
            "reason": "some reason",
            "skipped_alternatives": ["alt"],
            "risks": "",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        assert "risks" in body["error"]["details"]["missing_fields"]

    def test_override_missing_skipped_alternatives(self, session: MCPSession) -> None:
        """#7c — override_transition with empty skipped_alternatives returns REASON_REQUIRED."""
        _init_workflow(session)

        resp = session.call_tool("override_transition", {
            "target": "end",
            "reason": "some reason",
            "skipped_alternatives": [],
            "risks": "some risk",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        assert "skipped_alternatives" in body["error"]["details"]["missing_fields"]

    def test_override_missing_multiple_fields(self, session: MCPSession) -> None:
        """#7d — override_transition with multiple missing fields lists them all."""
        _init_workflow(session)

        resp = session.call_tool("override_transition", {
            "target": "end",
            "reason": "",
            "skipped_alternatives": [],
            "risks": "",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "REASON_REQUIRED"
        missing = body["error"]["details"]["missing_fields"]
        assert "reason" in missing
        assert "skipped_alternatives" in missing
        assert "risks" in missing


# ---------------------------------------------------------------------------
# Test 8: History distinguishes advance vs override vs reset
# ---------------------------------------------------------------------------

class TestHistoryDistinguishesOperations:
    def test_history_has_distinct_operation_types(self, session: MCPSession) -> None:
        """#8 — advance, override_transition, and reset_to each have distinct operation type."""
        _init_workflow(session)

        # advance: start → middle
        session.call_tool("advance", {"target": "middle"})

        # override: middle → end (legal, but using override)
        session.call_tool("override_transition", {
            "target": "end",
            "reason": "testing override",
            "skipped_alternatives": ["normal advance"],
            "risks": "none for test",
        })

        # reset: end → start
        session.call_tool("reset_to", {
            "state": "start",
            "trigger": "testing reset",
            "context": "verifying history",
        })

        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        entries = hist["data"]["entries"]

        # Should have: init, advance, override_transition, reset_to
        operations = [e["operation"] for e in entries]
        assert operations == ["init", "advance", "override_transition", "reset_to"]

        # Each type is distinct
        assert len(set(operations)) == 4


# ---------------------------------------------------------------------------
# Test 9: Full recovery cycle: block → reset → advance
# ---------------------------------------------------------------------------

class TestFullRecoveryCycle:
    def test_block_reset_advance_cycle(self, session: MCPSession) -> None:
        """#9 — Full cycle: init → advance to middle → block → reset to start → advance to middle."""
        _init_workflow(session)

        # Advance to middle
        resp = session.call_tool("advance", {"target": "middle"})
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "middle"

        # Block
        resp = session.call_tool("mark_blocked", {
            "blocker": "external dependency down",
            "unblock_condition": "dependency restored",
            "impact": "integration blocked",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["blocked"]["blocker"] == "external dependency down"

        # Advance should fail while blocked
        resp = session.call_tool("advance", {"target": "end"})
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "POSITION_BLOCKED"

        # Reset to start
        resp = session.call_tool("reset_to", {
            "state": "start",
            "trigger": "dependency recovered",
            "context": "restarting after fix",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "start"
        assert body["data"]["blocked_cleared"] is True

        # Advance to middle again — should work
        resp = session.call_tool("advance", {"target": "middle"})
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "middle"

        # Verify full history
        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        operations = [e["operation"] for e in hist["data"]["entries"]]
        assert operations == [
            "init",
            "advance",        # start → middle
            "mark_blocked",   # blocked
            "reset_to",       # middle → start
            "advance",        # start → middle again
        ]
        assert hist["data"]["count"] == 5
