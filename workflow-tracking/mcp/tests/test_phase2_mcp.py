"""Phase 2 acceptance tests: History + outputs over MCP stdio transport."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers (same transport layer as Phase 1)
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
# Test 1: Init creates history entry
# ---------------------------------------------------------------------------

class TestInitHistory:
    def test_init_creates_history_entry(self, session: MCPSession) -> None:
        """#1 — After init, history[0] has operation:'init', seq:1, timestamp, params."""
        _init_workflow(session)

        resp = session.call_tool("view_history")
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["count"] == 1

        entry = body["data"]["entries"][0]
        assert entry["seq"] == 1
        assert entry["operation"] == "init"
        assert "timestamp" in entry
        assert len(entry["timestamp"]) > 0
        # params should contain init-specific data
        assert "params" in entry
        assert entry["params"]["starting_state"] == "start"
        assert entry["params"]["capabilities"] == ["self"]
        assert entry["params"]["state_count"] == 3


# ---------------------------------------------------------------------------
# Test 2: Advance creates history entry
# ---------------------------------------------------------------------------

class TestAdvanceHistory:
    def test_advance_creates_history_entry(self, session: MCPSession) -> None:
        """#2 — Advance appends a history entry with from/to and monotonic seq."""
        _init_workflow(session)

        session.call_tool("advance", {"target": "middle"})

        resp = session.call_tool("view_history")
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["count"] == 2

        init_entry = body["data"]["entries"][0]
        advance_entry = body["data"]["entries"][1]

        # Monotonic seq
        assert init_entry["seq"] == 1
        assert advance_entry["seq"] == 2

        # Advance entry structure
        assert advance_entry["operation"] == "advance"
        assert advance_entry["params"]["from"] == "start"
        assert advance_entry["params"]["to"] == "middle"
        assert "timestamp" in advance_entry


# ---------------------------------------------------------------------------
# Test 3: record_output on visited state
# ---------------------------------------------------------------------------

class TestRecordOutputVisited:
    def test_record_output_on_visited_state(self, session: MCPSession) -> None:
        """#3 — record_output on a visited state stores output ref and appends history."""
        _init_workflow(session)

        # 'start' is visited by init
        resp = session.call_tool("record_output", {
            "state": "start",
            "output_ref": "artifacts/design.md",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["state"] == "start"
        assert body["data"]["output"]["ref"] == "artifacts/design.md"
        assert "recorded_at" in body["data"]["output"]
        assert body["data"]["total_outputs"] == 1

        # Verify history entry was appended
        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        assert hist["data"]["count"] == 2  # init + record_output

        output_entry = hist["data"]["entries"][1]
        assert output_entry["operation"] == "record_output"
        assert output_entry["params"]["state"] == "start"
        assert output_entry["params"]["output_ref"] == "artifacts/design.md"


# ---------------------------------------------------------------------------
# Test 4: record_output on unvisited state → STATE_NOT_VISITED
# ---------------------------------------------------------------------------

class TestRecordOutputUnvisited:
    def test_record_output_on_unvisited_state(self, session: MCPSession) -> None:
        """#4 — record_output on unvisited state returns STATE_NOT_VISITED."""
        _init_workflow(session)

        # 'middle' hasn't been visited yet
        resp = session.call_tool("record_output", {
            "state": "middle",
            "output_ref": "some-output",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "STATE_NOT_VISITED"


# ---------------------------------------------------------------------------
# Test 5: record_output on nonexistent state → STATE_NOT_FOUND
# ---------------------------------------------------------------------------

class TestRecordOutputNonexistent:
    def test_record_output_on_nonexistent_state(self, session: MCPSession) -> None:
        """#5 — record_output on nonexistent state returns STATE_NOT_FOUND."""
        _init_workflow(session)

        resp = session.call_tool("record_output", {
            "state": "bogus_state",
            "output_ref": "some-output",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "STATE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Test 6: view_history returns ordered entries
# ---------------------------------------------------------------------------

class TestViewHistoryOrdered:
    def test_view_history_returns_ordered_entries(self, session: MCPSession) -> None:
        """#6 — All entries in seq order, timestamps monotonic."""
        _init_workflow(session)
        session.call_tool("advance", {"target": "middle"})
        session.call_tool("record_output", {
            "state": "start",
            "output_ref": "out1",
        })
        session.call_tool("advance", {"target": "end"})

        resp = session.call_tool("view_history")
        body = _extract_content(resp)
        assert body["ok"] is True

        entries = body["data"]["entries"]
        assert len(entries) == 4  # init, advance, record_output, advance

        # Seq is strictly monotonic
        seqs = [e["seq"] for e in entries]
        assert seqs == [1, 2, 3, 4]

        # Timestamps are monotonically non-decreasing
        timestamps = [e["timestamp"] for e in entries]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1], (
                f"Timestamps not monotonic: {timestamps[i - 1]} > {timestamps[i]}"
            )


# ---------------------------------------------------------------------------
# Test 7: History is never truncated or modified
# ---------------------------------------------------------------------------

class TestHistoryImmutability:
    def test_history_never_truncated_or_modified(self, session: MCPSession) -> None:
        """#7 — After N operations, history has exactly N entries; no entry changes."""
        _init_workflow(session)

        # Snapshot after init (1 entry)
        resp = session.call_tool("view_history")
        snap1 = _extract_content(resp)["data"]["entries"]
        assert len(snap1) == 1

        # Advance (2 entries)
        session.call_tool("advance", {"target": "middle"})
        resp = session.call_tool("view_history")
        snap2 = _extract_content(resp)["data"]["entries"]
        assert len(snap2) == 2
        # First entry unchanged
        assert snap2[0] == snap1[0]

        # Record output (3 entries)
        session.call_tool("record_output", {
            "state": "start",
            "output_ref": "out-a",
        })
        resp = session.call_tool("view_history")
        snap3 = _extract_content(resp)["data"]["entries"]
        assert len(snap3) == 3
        # Previous entries unchanged
        assert snap3[0] == snap1[0]
        assert snap3[1] == snap2[1]

        # Another advance (4 entries)
        session.call_tool("advance", {"target": "end"})
        resp = session.call_tool("view_history")
        snap4 = _extract_content(resp)["data"]["entries"]
        assert len(snap4) == 4
        # All previous entries unchanged
        assert snap4[0] == snap1[0]
        assert snap4[1] == snap2[1]
        assert snap4[2] == snap3[2]

        # Another record_output (5 entries)
        session.call_tool("record_output", {
            "state": "end",
            "output_ref": "out-b",
        })
        resp = session.call_tool("view_history")
        snap5 = _extract_content(resp)["data"]["entries"]
        assert len(snap5) == 5
        for i in range(4):
            assert snap5[i] == snap4[i], f"Entry {i} was mutated"


# ---------------------------------------------------------------------------
# Test 8: Multiple outputs per state
# ---------------------------------------------------------------------------

class TestMultipleOutputsPerState:
    def test_multiple_outputs_per_state(self, session: MCPSession) -> None:
        """#8 — Multiple record_output calls append to same state's output array."""
        _init_workflow(session)

        refs = ["output-1.md", "output-2.md", "output-3.md"]
        for i, ref in enumerate(refs, 1):
            resp = session.call_tool("record_output", {
                "state": "start",
                "output_ref": ref,
            })
            body = _extract_content(resp)
            assert body["ok"] is True
            assert body["data"]["total_outputs"] == i
            assert body["data"]["output"]["ref"] == ref

        # Verify history has init + 3 record_outputs = 4 entries
        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        assert hist["data"]["count"] == 4
        # All 3 record_output entries present
        output_entries = [
            e for e in hist["data"]["entries"] if e["operation"] == "record_output"
        ]
        assert len(output_entries) == 3
        recorded_refs = [e["params"]["output_ref"] for e in output_entries]
        assert recorded_refs == refs
