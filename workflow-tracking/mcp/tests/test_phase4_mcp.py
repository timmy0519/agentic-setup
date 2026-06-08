"""Phase 4 acceptance tests: Workflow evolution over MCP stdio transport."""

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

INITIAL_WORKFLOW = """\
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

# Updated workflow that PRESERVES "middle"
UPDATED_WORKFLOW_PRESERVES = """\
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

# Updated workflow that REMOVES "middle"
UPDATED_WORKFLOW_REMOVES_MIDDLE = """\
states:
  start:
    handler_type: self
    transitions:
      - review
    input: "Initial state"
    output: "Ready for review"
  review:
    handler_type: self
    transitions:
      - end
    input: "Output from start"
    output: "Ready for end"
  end:
    handler_type: self
    transitions: []
    input: "Output from review"
    output: "Final result"
"""

# Workflow with a capability violation (uses "agent" handler not declared)
WORKFLOW_CAPABILITY_VIOLATION = """\
states:
  start:
    handler_type: agent
    transitions:
      - end
    input: "Initial state"
    output: "Ready for end"
  end:
    handler_type: self
    transitions: []
    input: "Output from start"
    output: "Final result"
"""

# Second update for multiple-cycle testing
UPDATED_WORKFLOW_V3 = """\
states:
  start:
    handler_type: self
    transitions:
      - review
    input: "Initial state"
    output: "Ready for review"
  review:
    handler_type: self
    transitions:
      - qa
    input: "Output from start"
    output: "Ready for QA"
  qa:
    handler_type: self
    transitions:
      - end
    input: "Output from review"
    output: "Ready for end"
  end:
    handler_type: self
    transitions: []
    input: "Output from QA"
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
        "workflow_yaml": INITIAL_WORKFLOW,
    })
    body = _extract_content(resp)
    assert body["ok"] is True
    return body


# ---------------------------------------------------------------------------
# Test 1: update_workflow — current state preserved
# ---------------------------------------------------------------------------

class TestUpdateWorkflowCurrentStatePreserved:
    def test_update_preserves_current_state(self, session: MCPSession) -> None:
        """#1 — Old workflow archived in versions[]; new workflow active; version incremented; history entry with reason."""
        _init_workflow(session)

        # Advance to middle so current_state = "middle"
        resp = session.call_tool("advance", {"target": "middle"})
        body = _extract_content(resp)
        assert body["ok"] is True

        # Update workflow — "middle" still exists in new workflow
        resp = session.call_tool("update_workflow", {
            "workflow_yaml": UPDATED_WORKFLOW_PRESERVES,
            "reason": "adding review step after middle",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["old_version"] == 1
        assert body["data"]["new_version"] == 2
        assert body["data"]["current_state"] == "middle"
        assert "review" in body["data"]["added_states"]

        # Verify history entry includes reason
        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        update_entry = hist["data"]["entries"][-1]
        assert update_entry["operation"] == "update_workflow"
        assert "adding review step" in update_entry["params"]["reason"]

        # Verify old workflow is archived in versions
        resp = session.call_tool("view_workflow", {"version": 1})
        v1 = _extract_content(resp)
        assert v1["ok"] is True
        assert v1["data"]["version"]["version"] == 1
        assert "middle" in v1["data"]["version"]["yaml"]
        assert "review" not in v1["data"]["version"]["yaml"]

        # Verify new workflow is active
        resp = session.call_tool("view_workflow")
        wf = _extract_content(resp)
        assert wf["data"]["version"] == 2
        assert "review" in wf["data"]["yaml"]
        assert "middle" in wf["data"]["yaml"]

    def test_transitions_update_after_workflow_change(self, session: MCPSession) -> None:
        """#1b — After update, legal transitions reflect the new workflow graph."""
        _init_workflow(session)
        session.call_tool("advance", {"target": "middle"})

        # Before update: middle → end
        resp = session.call_tool("view_legal_transitions")
        body = _extract_content(resp)
        assert "end" in body["data"]["transitions"]

        # Update: middle now → review (not end)
        session.call_tool("update_workflow", {
            "workflow_yaml": UPDATED_WORKFLOW_PRESERVES,
            "reason": "reroute middle to review",
        })

        # After update: middle → review
        resp = session.call_tool("view_legal_transitions")
        body = _extract_content(resp)
        assert "review" in body["data"]["transitions"]


# ---------------------------------------------------------------------------
# Test 2: update_workflow — current state removed, reset_to_state provided
# ---------------------------------------------------------------------------

class TestUpdateWorkflowResetToState:
    def test_atomic_reset_and_update(self, session: MCPSession) -> None:
        """#2 — Atomic: position resets + workflow updates in one write; history shows combined entry."""
        _init_workflow(session)

        # Advance to middle
        session.call_tool("advance", {"target": "middle"})

        # Update workflow — removes "middle", reset to "start"
        resp = session.call_tool("update_workflow", {
            "workflow_yaml": UPDATED_WORKFLOW_REMOVES_MIDDLE,
            "reason": "removing middle, resetting to start",
            "reset_to_state": "start",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["current_state"] == "start"
        assert "middle" in body["data"]["removed_states"]

        # Verify history shows combined entry (workflow update + reset)
        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        update_entry = hist["data"]["entries"][-1]
        assert update_entry["operation"] == "update_workflow"
        assert update_entry["params"]["reason"] == "removing middle, resetting to start"

        # Verify current state is actually reset
        resp = session.call_tool("view_current_state")
        state = _extract_content(resp)
        assert state["data"]["current_state"] == "start"

        # Verify "middle" no longer in workflow
        resp = session.call_tool("view_workflow")
        wf = _extract_content(resp)
        assert "middle" not in wf["data"]["yaml"]


# ---------------------------------------------------------------------------
# Test 3: update_workflow — current state removed, no reset_to_state
# ---------------------------------------------------------------------------

class TestUpdateWorkflowCurrentStateRemovedNoReset:
    def test_returns_current_state_removed(self, session: MCPSession) -> None:
        """#3 — Returns CURRENT_STATE_REMOVED listing surviving states."""
        _init_workflow(session)

        # Advance to middle
        session.call_tool("advance", {"target": "middle"})

        # Update workflow — removes "middle" but no reset_to_state
        resp = session.call_tool("update_workflow", {
            "workflow_yaml": UPDATED_WORKFLOW_REMOVES_MIDDLE,
            "reason": "removing middle without reset",
        })
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "CURRENT_STATE_REMOVED"

        # Error should list surviving states for the caller to pick from
        details = body["error"].get("details", {})
        surviving = details.get("surviving_states") or details.get("available_states") or []
        # At minimum, the new workflow's states should be listed somewhere in the error
        error_text = json.dumps(body["error"])
        assert "start" in error_text or "review" in error_text or "end" in error_text

        # Workflow should NOT have been updated (atomic — rejected)
        resp = session.call_tool("view_workflow")
        wf = _extract_content(resp)
        assert wf["data"]["version"] == 1
        assert "middle" in wf["data"]["yaml"]


# ---------------------------------------------------------------------------
# Test 4: update_workflow with capability violation
# ---------------------------------------------------------------------------

class TestUpdateWorkflowCapabilityViolation:
    def test_update_unions_new_handler_capabilities(self, session: MCPSession) -> None:
        """#4 — Permissive (NFR3/KD10): reshaping a member to use a new handler
        unions that handler into session caps instead of refusing. Capabilities
        are a descriptive record, not a gate."""
        _init_workflow(session)  # capabilities = ["self"]

        # Update with a workflow using the "agent" handler (previously undeclared)
        resp = session.call_tool("update_workflow", {
            "workflow_yaml": WORKFLOW_CAPABILITY_VIOLATION,
            "reason": "switching to agent handlers",
        })
        body = _extract_content(resp)
        assert body["ok"] is True

        # Workflow was reshaped + archived; the new handler is now in session caps
        resp = session.call_tool("view_workflow")
        wf = _extract_content(resp)
        assert wf["data"]["version"] == 2


# ---------------------------------------------------------------------------
# Test 5: view_version(1) after update
# ---------------------------------------------------------------------------

class TestViewVersionAfterUpdate:
    def test_view_version_returns_original_workflow(self, session: MCPSession) -> None:
        """#5 — view_version(1) returns original workflow definition (full copy)."""
        _init_workflow(session)

        # Record the original workflow YAML
        resp = session.call_tool("view_workflow")
        original_wf = _extract_content(resp)
        original_yaml = original_wf["data"]["yaml"]
        assert original_wf["data"]["version"] == 1

        # Update workflow
        session.call_tool("update_workflow", {
            "workflow_yaml": UPDATED_WORKFLOW_PRESERVES,
            "reason": "adding review step",
        })

        # view_version(1) should return the original
        resp = session.call_tool("view_workflow", {"version": 1})
        body = _extract_content(resp)
        assert body["ok"] is True
        v1 = body["data"]["version"]
        assert v1["version"] == 1
        # Original had start, middle, end but not review
        assert "middle" in v1["yaml"]
        assert "review" not in v1["yaml"]

        # Confirm version 2 is different (current)
        resp = session.call_tool("view_workflow", {"version": 2})
        body = _extract_content(resp)
        assert body["ok"] is True
        v2 = body["data"]["version"]
        assert v2["version"] == 2
        assert "review" in v2["yaml"]

    def test_view_nonexistent_version_returns_error(self, session: MCPSession) -> None:
        """#5b — view_version for nonexistent version returns VERSION_NOT_FOUND."""
        _init_workflow(session)

        resp = session.call_tool("view_workflow", {"version": 99})
        body = _extract_content(resp)
        assert body["ok"] is False
        assert body["error"]["code"] == "VERSION_NOT_FOUND"


# ---------------------------------------------------------------------------
# Test 6: Orphaned output refs after state removal
# ---------------------------------------------------------------------------

class TestOrphanedOutputRefs:
    def test_orphaned_outputs_preserved_in_history(self, session: MCPSession) -> None:
        """#6 — Refs preserved in history; removed from active position.outputs."""
        _init_workflow(session)

        # Advance to middle and record output there
        session.call_tool("advance", {"target": "middle"})
        session.call_tool("record_output", {
            "state": "middle",
            "output_ref": "artifacts/middle-output.md",
        })

        # Also record on start (visited during init)
        session.call_tool("record_output", {
            "state": "start",
            "output_ref": "artifacts/start-output.md",
        })

        # Update workflow removing "middle", reset to "start"
        resp = session.call_tool("update_workflow", {
            "workflow_yaml": UPDATED_WORKFLOW_REMOVES_MIDDLE,
            "reason": "removing middle state",
            "reset_to_state": "start",
        })
        body = _extract_content(resp)
        assert body["ok"] is True

        # Orphaned outputs from "middle" should be reported
        orphaned = body["data"].get("orphaned_outputs", {})
        assert "middle" in orphaned
        orphaned_refs = [o["ref"] for o in orphaned["middle"]]
        assert "artifacts/middle-output.md" in orphaned_refs

        # History should preserve the orphaned output refs
        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        update_entry = hist["data"]["entries"][-1]
        assert update_entry["operation"] == "update_workflow"
        hist_orphaned = update_entry["params"].get("orphaned_outputs", {})
        assert "middle" in hist_orphaned


# ---------------------------------------------------------------------------
# Test 7: view_workflow returns Mermaid
# ---------------------------------------------------------------------------

class TestViewWorkflowMermaid:
    def test_view_workflow_includes_mermaid(self, session: MCPSession) -> None:
        """#7 — Response includes valid Mermaid string matching current graph structure."""
        _init_workflow(session)

        resp = session.call_tool("view_workflow")
        body = _extract_content(resp)
        assert body["ok"] is True

        mermaid = body["data"]["mermaid"]
        assert "stateDiagram-v2" in mermaid

        # Should include all states
        assert "start" in mermaid
        assert "middle" in mermaid
        assert "end" in mermaid

        # Should include transitions
        assert "-->" in mermaid

        # Terminal state (end) should have arrow to [*]
        assert "[*]" in mermaid

    def test_mermaid_updates_after_workflow_change(self, session: MCPSession) -> None:
        """#7b — Mermaid reflects updated workflow after update_workflow."""
        _init_workflow(session)

        session.call_tool("update_workflow", {
            "workflow_yaml": UPDATED_WORKFLOW_PRESERVES,
            "reason": "adding review step",
        })

        resp = session.call_tool("view_workflow")
        body = _extract_content(resp)
        mermaid = body["data"]["mermaid"]

        # New state "review" should appear
        assert "review" in mermaid
        # All 4 states present
        assert "start" in mermaid
        assert "middle" in mermaid
        assert "end" in mermaid

    def test_yaml_round_trip(self, session: MCPSession) -> None:
        """#7c — YAML from view_workflow is directly resubmittable (round-trip safe)."""
        _init_workflow(session)

        # Get current workflow YAML
        resp = session.call_tool("view_workflow")
        body = _extract_content(resp)
        returned_yaml = body["data"]["yaml"]

        # Submit it back as an update — should parse and validate
        resp = session.call_tool("update_workflow", {
            "workflow_yaml": returned_yaml,
            "reason": "round-trip test",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["new_version"] == 2

        # View the updated workflow — YAML should be equivalent
        resp = session.call_tool("view_workflow")
        body = _extract_content(resp)
        assert body["data"]["version"] == 2
        assert "start" in body["data"]["yaml"]
        assert "middle" in body["data"]["yaml"]
        assert "end" in body["data"]["yaml"]


# ---------------------------------------------------------------------------
# Test 8: Multiple update cycles
# ---------------------------------------------------------------------------

class TestMultipleUpdateCycles:
    def test_versions_array_grows_and_snapshots_correct(self, session: MCPSession) -> None:
        """#8 — versions array grows; each view_version(n) returns correct snapshot."""
        _init_workflow(session)

        # --- Update 1: v1 → v2 (add "review") ---
        resp = session.call_tool("update_workflow", {
            "workflow_yaml": UPDATED_WORKFLOW_PRESERVES,
            "reason": "first update: add review",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["new_version"] == 2

        # --- Update 2: v2 → v3 (add "qa", remove "middle") ---
        # Current state is "start", so removing "middle" is fine
        resp = session.call_tool("update_workflow", {
            "workflow_yaml": UPDATED_WORKFLOW_V3,
            "reason": "second update: add qa, remove middle",
        })
        body = _extract_content(resp)
        assert body["ok"] is True
        assert body["data"]["new_version"] == 3

        # --- Verify all versions ---

        # Version 1: original (start, middle, end)
        resp = session.call_tool("view_workflow", {"version": 1})
        v1 = _extract_content(resp)
        assert v1["ok"] is True
        v1_yaml = v1["data"]["version"]["yaml"]
        assert "start" in v1_yaml and "middle" in v1_yaml and "end" in v1_yaml
        assert "review" not in v1_yaml

        # Version 2: first update (start, middle, review, end)
        resp = session.call_tool("view_workflow", {"version": 2})
        v2 = _extract_content(resp)
        assert v2["ok"] is True
        v2_yaml = v2["data"]["version"]["yaml"]
        assert "middle" in v2_yaml and "review" in v2_yaml

        # Version 3: second update (start, review, qa, end) — current
        resp = session.call_tool("view_workflow", {"version": 3})
        v3 = _extract_content(resp)
        assert v3["ok"] is True
        v3_yaml = v3["data"]["version"]["yaml"]
        assert "qa" in v3_yaml and "review" in v3_yaml
        assert "middle" not in v3_yaml

        # Current workflow matches v3
        resp = session.call_tool("view_workflow")
        wf = _extract_content(resp)
        assert wf["data"]["version"] == 3
        assert "qa" in wf["data"]["yaml"]
        assert "middle" not in wf["data"]["yaml"]

    def test_history_tracks_all_updates(self, session: MCPSession) -> None:
        """#8b — History has entries for each update_workflow call."""
        _init_workflow(session)

        session.call_tool("update_workflow", {
            "workflow_yaml": UPDATED_WORKFLOW_PRESERVES,
            "reason": "first update",
        })
        session.call_tool("update_workflow", {
            "workflow_yaml": UPDATED_WORKFLOW_V3,
            "reason": "second update",
        })

        resp = session.call_tool("view_history")
        hist = _extract_content(resp)
        operations = [e["operation"] for e in hist["data"]["entries"]]
        assert operations.count("update_workflow") == 2
