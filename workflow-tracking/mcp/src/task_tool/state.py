"""Position tracking and file I/O for workflow state."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

from .errors import (
    ALREADY_INITIALIZED,
    BRANCH_UNKNOWN,
    CAPABILITY_MISMATCH,
    CURRENT_STATE_REMOVED,
    ILLEGAL_TRANSITION,
    INVALID_STRUCTURE,
    JOIN_STATE_REQUIRED,
    META_KEY_EXISTS,
    NO_WORKFLOW,
    POSITION_BLOCKED,
    REASON_REQUIRED,
    STATE_NOT_FOUND,
    STATE_NOT_VISITED,
    VERSION_NOT_FOUND,
    WORKFLOW_NOT_REGISTERED,
    make_error,
    make_success,
)
from .history import make_entry, next_seq, _now_iso
from .models import (
    Meta,
    Position,
    WorkflowEntry,
    WorkflowState,
    WorkflowStateFile,
    StateDefinition,
)
from .yaml_parser import parse_workflow_yaml
from .validator import validate_graph

STATE_DIR = ".task-tool"
STATE_FILE = "workflow-state.json"

# Default registry key — init's supplied graph becomes this member (KD1).
DEFAULT_META_KEY = "artifact-flow"

# Module-level session tracking — set by init or resume, reset between tests
_active_session_path: Path | None = None


def _base_dir() -> Path:
    """Return the base directory for state files."""
    if "TASK_TOOL_WORKDIR" in os.environ:
        return Path(os.environ["TASK_TOOL_WORKDIR"])
    return Path.cwd()


def _state_path() -> Path:
    """Return the active session's state file path.

    After init or resume, returns the session-scoped path.
    Before either, returns a fallback path that won't exist.
    """
    if _active_session_path is not None:
        return _active_session_path
    return _base_dir() / STATE_DIR / STATE_FILE


def _reset_session() -> None:
    """Reset the active session. Used by test fixtures."""
    global _active_session_path
    _active_session_path = None


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically: write to temp file, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".tmp-state-",
        suffix=".json",
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, str(path))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_state() -> WorkflowStateFile | None:
    """Load existing state file, or return None if no active session."""
    if _active_session_path is None:
        return None
    if not _active_session_path.exists():
        return None
    with open(_active_session_path) as f:
        data = json.load(f)
    return WorkflowStateFile.from_dict(data)


def _compute_status(
    position: Position,
    graph: dict[str, StateDefinition],
) -> str:
    """Derive status for a single registry member from its position + graph."""
    if position.blocked is not None:
        return "blocked"
    current_def = graph.get(position.current_state)
    if current_def is not None and not current_def.transitions:
        return "done"
    return "active"


def _rollup_status(wsf: WorkflowStateFile) -> str:
    """Session-level status rollup across all registry members (KD1).

    blocked if any member is blocked, else active if any is active, else done.
    """
    statuses = [
        _compute_status(entry.position, entry.workflow.states)
        for entry in wsf.workflows.values()
    ]
    if not statuses:
        return "done"
    if "blocked" in statuses:
        return "blocked"
    if "active" in statuses:
        return "active"
    return "done"


def _resolve_member(
    wsf: WorkflowStateFile,
    meta_key: str,
) -> tuple[WorkflowEntry | None, dict | None]:
    """Resolve a registry member by meta_key.

    Returns:
        (entry, None) on success, or (None, error_dict) if not registered.
    """
    entry = wsf.workflows.get(meta_key)
    if entry is None:
        return None, make_error(
            WORKFLOW_NOT_REGISTERED,
            f"No workflow registered under meta_key '{meta_key}'.",
            details={"meta_key": meta_key, "registered": list(wsf.workflows.keys())},
            guidance="Use a registered meta_key, or call register_workflow / init to create one.",
        )
    return entry, None


def init_state(
    capabilities: list[str],
    graph: dict[str, StateDefinition],
    title: str = "",
    description: str = "",
    assignee: str = "",
    meta_key: str = DEFAULT_META_KEY,
) -> dict:
    """Initialize a new workflow state file.

    Creates a session-scoped state file at
    ``<base>/.task-tool/<session-id>/workflow-state.json``.

    The supplied graph becomes the ``artifact-flow`` registry member by
    default (KD1); pass an explicit ``meta_key`` to bootstrap the session
    under a different key. Further members are added with ``register_workflow``.

    Args:
        capabilities: Declared capability list.
        graph: Parsed and validated state graph.
        title: Short descriptive title for this workflow.
        description: Brief description of what this workflow will accomplish.
        assignee: Short identifier for the workflow owner.
        meta_key: Registry key for the initial member (default "artifact-flow").

    Returns:
        Success or error dict.  Includes ``state_file`` path for resume.
    """
    global _active_session_path

    if _active_session_path is not None:
        return make_error(
            ALREADY_INITIALIZED,
            "Workflow is already initialized.",
            details={"state_file": str(_active_session_path)},
            guidance="A session is already active. Use advance to move through states, or resume to attach to a different session.",
        )

    # First key in the ordered dict is the starting state
    first_state = next(iter(graph))
    now = _now_iso()
    session_id = str(uuid.uuid4())

    # Session-scoped path
    session_path = _base_dir() / STATE_DIR / session_id / STATE_FILE

    init_entry = make_entry(
        seq=1,
        operation="init",
        params={
            "meta_key": meta_key,
            "capabilities": capabilities,
            "starting_state": first_state,
            "state_count": len(graph),
        },
    )

    position = Position(
        current_state=first_state,
        visited=[first_state],
    )

    entry = WorkflowEntry(
        workflow=WorkflowState(version=1, states=graph),
        position=position,
    )

    state_file = WorkflowStateFile(
        meta=Meta(
            schema_version=2,
            created_at=now,
            session_id=session_id,
            capabilities=capabilities,
            title=title,
            description=description,
            assignee=assignee,
            status=_compute_status(position, graph),
        ),
        workflows={meta_key: entry},
        history=[init_entry],
        versions=[],
    )

    _atomic_write(session_path, state_file.to_dict())
    _active_session_path = session_path

    return make_success({
        "session_id": session_id,
        "meta_key": meta_key,
        "current_state": first_state,
        "transitions": graph[first_state].transitions,
        "state_file": str(session_path),
    })


def advance(target: str, summary: str = "", meta_key: str = DEFAULT_META_KEY) -> dict:
    """Advance to a target state.

    Args:
        target: The state to transition to.
        summary: Summary of what was accomplished and current context
            (<500 words). Write as if a stateless replacement agent will
            read ONLY this summary to understand where things stand.
        meta_key: Registry member to operate on (default "artifact-flow").

    Returns:
        Success or error dict.
    """
    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    # Check blocked BEFORE transition legality
    if entry.position.blocked is not None:
        blocked = entry.position.blocked
        return make_error(
            POSITION_BLOCKED,
            f"Workflow is blocked — blocker: {blocked['blocker']}; unblock when: {blocked['unblock_condition']}; impact: {blocked['impact']}",
            details={
                "current_state": entry.position.current_state,
                "blocked": blocked,
            },
            guidance="Use reset_to or override_transition to recover.",
        )

    current = entry.position.current_state
    current_def = entry.workflow.states.get(current)
    if current_def is None:
        return make_error(
            NO_WORKFLOW,
            f"Current state '{current}' not found in workflow.",
            guidance="The state file may be corrupted.",
        )

    if target not in current_def.transitions:
        return make_error(
            ILLEGAL_TRANSITION,
            f"Cannot transition from '{current}' to '{target}'.",
            details={
                "current_state": current,
                "target": target,
                "legal_transitions": current_def.transitions,
            },
            guidance=f"Legal transitions from '{current}': {current_def.transitions}",
        )

    # Soft gate (KD5): entering a gate:true DESTINATION state without
    # has-review-subagent-checked evidence returns a SOFT recommendation
    # (not a refusal) routing the lead to advance_without_evidence. The
    # gate never hard-refuses — this is a typed success carrying guidance.
    target_def = entry.workflow.states[target]
    if target_def.gate:
        evidence = entry.position.gate_evidence.get(target, {}) or {}
        if not evidence.get("has-review-subagent-checked"):
            return make_success({
                "soft_gate": True,
                "advanced": False,
                "current_state": current,
                "target": target,
                "recommendation": (
                    f"'{target}' is an AC gate. No has-review-subagent-checked "
                    "evidence is recorded for it. Record review evidence with "
                    "record_review_evidence(meta_key, gate_state) and retry "
                    "advance, OR proceed deliberately with "
                    f"advance_without_evidence(target='{target}', reason=...) — "
                    "the reason is logged for audit. This is a recommendation, "
                    "not a block."
                ),
            })

    # Join reset on rework re-entry (KD3): re-entering a convergence state, or
    # a predecessor of one, via a back-edge clears that convergence state's
    # received set so a prior pass cannot falsely re-surface a ready gate.
    # _move_to enforces this invariant for every move site.
    _move_to(entry, target)

    # Update exec_summary if provided
    if summary:
        wsf.meta.exec_summary = summary

    history_params: dict = {"meta_key": meta_key, "from": current, "to": target}
    if summary:
        history_params["summary"] = summary

    wsf.history.append(
        make_entry(
            seq=next_seq(wsf.history),
            operation="advance",
            params=history_params,
        )
    )

    # Update auto-derived session rollup status
    wsf.meta.status = _rollup_status(wsf)

    _atomic_write(_state_path(), wsf.to_dict())

    target_def = entry.workflow.states[target]
    result_data: dict = {
        "previous_state": current,
        "current_state": target,
        "transitions": target_def.transitions,
    }

    # Soft validate summary length
    if summary:
        word_count = len(summary.split())
        if word_count > 500:
            result_data["warning"] = (
                f"exec_summary is {word_count} words, exceeding the recommended 500-word limit. "
                "Consider trimming to reference file paths instead of dumping content inline."
            )

    return make_success(result_data)


def get_current_state(meta_key: str = DEFAULT_META_KEY) -> dict:
    """Return the current state name.

    Args:
        meta_key: Registry member to read (default "artifact-flow").

    Returns:
        Success or error dict.
    """
    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    return make_success({"current_state": entry.position.current_state})


def get_legal_transitions(meta_key: str = DEFAULT_META_KEY) -> dict:
    """Return legal transitions from the current state.

    Args:
        meta_key: Registry member to read (default "artifact-flow").

    Returns:
        Success or error dict.
    """
    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    current = entry.position.current_state
    current_def = entry.workflow.states.get(current)
    if current_def is None:
        return make_error(
            NO_WORKFLOW,
            f"Current state '{current}' not found in workflow.",
            guidance="The state file may be corrupted.",
        )

    return make_success({
        "current_state": current,
        "transitions": current_def.transitions,
    })


def record_output(
    state: str, output_ref: str, meta_key: str = DEFAULT_META_KEY
) -> dict:
    """Record an output reference for a visited state.

    Args:
        state: The state to attach the output to.
        output_ref: An output reference string (URI, path, etc.).
        meta_key: Registry member to operate on (default "artifact-flow").

    Returns:
        Success or error dict.
    """
    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    # Check state exists in the workflow
    if state not in entry.workflow.states:
        return make_error(
            STATE_NOT_FOUND,
            f"State '{state}' does not exist in the workflow.",
            details={"state": state, "known_states": list(entry.workflow.states.keys())},
            guidance="Use a state name defined in the workflow YAML.",
        )

    # Check state has been visited
    if state not in entry.position.visited:
        return make_error(
            STATE_NOT_VISITED,
            f"State '{state}' has not been visited yet.",
            details={"state": state, "visited": entry.position.visited},
            guidance="Advance to a state before recording outputs for it.",
        )

    # Build structured output ref
    now = _now_iso()
    output_record = {"ref": output_ref, "recorded_at": now}

    # Append output ref
    if state not in entry.position.outputs:
        entry.position.outputs[state] = []
    entry.position.outputs[state].append(output_record)

    # Append history entry
    wsf.history.append(
        make_entry(
            seq=next_seq(wsf.history),
            operation="record_output",
            params={"meta_key": meta_key, "state": state, "output_ref": output_ref},
        )
    )

    _atomic_write(_state_path(), wsf.to_dict())

    return make_success({
        "state": state,
        "output": output_record,
        "total_outputs": len(entry.position.outputs[state]),
    })


def view_history(meta_key: str | None = None) -> dict:
    """Return the append-only history array.

    History is file-global (shared across all registry members, tagged with
    ``meta_key`` per entry). Pass ``meta_key`` to filter to entries for that
    member; pass ``None`` (default) for the full unfiltered log.

    A member-filtered view includes BOTH (a) entries tagged with that meta_key
    AND (b) session-level ops that carry no member tag at all (update_meta,
    resume). Session-scoped ops are cross-cutting — they belong to no single
    member, so they must appear in every member's filtered view rather than
    silently dropping out of the per-member audit trail.

    Args:
        meta_key: If set, return entries whose params carry this meta_key plus
            any untagged (session-level) entries.

    Returns:
        Success or error dict.
    """
    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entries = wsf.history
    if meta_key is not None:
        # Keep member-tagged entries for this meta_key, plus untagged
        # session-level ops (no meta_key in params) which are cross-cutting.
        entries = [
            h
            for h in entries
            if h.params.get("meta_key") == meta_key or "meta_key" not in h.params
        ]

    return make_success({
        "entries": [h.to_dict() for h in entries],
        "count": len(entries),
    })


def mark_blocked(
    blocker: str,
    unblock_condition: str,
    impact: str,
    meta_key: str = DEFAULT_META_KEY,
) -> dict:
    """Mark the current workflow position as blocked.

    Args:
        blocker: What is preventing progress (required, non-empty).
        unblock_condition: What needs to happen for this to unblock (required, non-empty).
        impact: What is affected or delayed while blocked (required, non-empty).
        meta_key: Registry member to operate on (default "artifact-flow").

    Returns:
        Success or error dict.
    """
    missing = []
    if not blocker or not blocker.strip():
        missing.append("blocker")
    if not unblock_condition or not unblock_condition.strip():
        missing.append("unblock_condition")
    if not impact or not impact.strip():
        missing.append("impact")

    if missing:
        return make_error(
            REASON_REQUIRED,
            f"Required fields missing or empty: {', '.join(missing)}.",
            details={"missing_fields": missing},
            guidance="All fields (blocker, unblock_condition, impact) are required for mark_blocked.",
        )

    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    blocked_info = {
        "blocker": blocker,
        "unblock_condition": unblock_condition,
        "impact": impact,
    }
    entry.position.blocked = blocked_info
    wsf.meta.status = _rollup_status(wsf)

    wsf.history.append(
        make_entry(
            seq=next_seq(wsf.history),
            operation="mark_blocked",
            params={
                "meta_key": meta_key,
                "state": entry.position.current_state,
                "blocker": blocker,
                "unblock_condition": unblock_condition,
                "impact": impact,
            },
        )
    )

    _atomic_write(_state_path(), wsf.to_dict())

    return make_success({
        "current_state": entry.position.current_state,
        "blocked": blocked_info,
    })


def reset_to(
    state: str, trigger: str, context: str, meta_key: str = DEFAULT_META_KEY
) -> dict:
    """Force-move the workflow to any existing state, clearing blocked.

    Args:
        state: Target state to reset to (must exist in workflow).
        trigger: What changed or was resolved that caused this reset (required, non-empty).
        context: Key information or situation that led to this decision (required, non-empty).
        meta_key: Registry member to operate on (default "artifact-flow").

    Returns:
        Success or error dict.
    """
    missing = []
    if not trigger or not trigger.strip():
        missing.append("trigger")
    if not context or not context.strip():
        missing.append("context")

    if missing:
        return make_error(
            REASON_REQUIRED,
            f"Required fields missing or empty: {', '.join(missing)}.",
            details={"missing_fields": missing},
            guidance="All fields (trigger, context) are required for reset_to.",
        )

    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    if state not in entry.workflow.states:
        return make_error(
            STATE_NOT_FOUND,
            f"State '{state}' does not exist in the workflow.",
            details={"state": state, "known_states": list(entry.workflow.states.keys())},
            guidance="Use a state name defined in the workflow YAML.",
        )

    previous = entry.position.current_state
    was_blocked = entry.position.blocked

    # Rework re-entry must clear stale per-pass join accumulators (KD3, DEFECT #1);
    # _move_to enforces this invariant. reset_to additionally clears blocked.
    _move_to(entry, state)
    entry.position.blocked = None

    wsf.meta.status = _rollup_status(wsf)

    wsf.history.append(
        make_entry(
            seq=next_seq(wsf.history),
            operation="reset_to",
            params={
                "meta_key": meta_key,
                "from": previous,
                "to": state,
                "trigger": trigger,
                "context": context,
                "was_blocked": was_blocked,
            },
        )
    )

    _atomic_write(_state_path(), wsf.to_dict())

    target_def = entry.workflow.states[state]
    return make_success({
        "previous_state": previous,
        "current_state": state,
        "transitions": target_def.transitions,
        "blocked_cleared": was_blocked is not None,
    })


def override_transition(
    target: str,
    reason: str,
    skipped_alternatives: list[str],
    risks: str,
    meta_key: str = DEFAULT_META_KEY,
) -> dict:
    """Force-move to a target state, bypassing transition rules.

    All parameters are required and documented in history for auditability.

    Args:
        target: Target state (must exist in workflow).
        reason: Why this override is needed.
        skipped_alternatives: What alternatives were considered and rejected.
        risks: Known risks of this override.
        meta_key: Registry member to operate on (default "artifact-flow").

    Returns:
        Success or error dict.
    """
    # Validate all required fields
    missing = []
    if not reason or not reason.strip():
        missing.append("reason")
    if not skipped_alternatives:
        missing.append("skipped_alternatives")
    if not risks or not risks.strip():
        missing.append("risks")

    if missing:
        return make_error(
            REASON_REQUIRED,
            f"Required fields missing or empty: {', '.join(missing)}.",
            details={"missing_fields": missing},
            guidance="All fields (reason, skipped_alternatives, risks) are required for override_transition.",
        )

    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    if target not in entry.workflow.states:
        return make_error(
            STATE_NOT_FOUND,
            f"State '{target}' does not exist in the workflow.",
            details={"state": target, "known_states": list(entry.workflow.states.keys())},
            guidance="Use a state name defined in the workflow YAML.",
        )

    previous = entry.position.current_state
    was_blocked = entry.position.blocked

    # Force-move re-entry must clear stale per-pass join accumulators (KD3,
    # DEFECT #1); _move_to enforces this invariant. override additionally clears
    # blocked. (This was the 4th move site that previously skipped the reset.)
    _move_to(entry, target)
    entry.position.blocked = None

    wsf.meta.status = _rollup_status(wsf)

    wsf.history.append(
        make_entry(
            seq=next_seq(wsf.history),
            operation="override_transition",
            params={
                "meta_key": meta_key,
                "from": previous,
                "to": target,
                "reason": reason,
                "skipped_alternatives": skipped_alternatives,
                "risks": risks,
                "was_blocked": was_blocked,
            },
        )
    )

    _atomic_write(_state_path(), wsf.to_dict())

    target_def = entry.workflow.states[target]
    return make_success({
        "previous_state": previous,
        "current_state": target,
        "transitions": target_def.transitions,
        "blocked_cleared": was_blocked is not None,
    })


def _generate_yaml(graph: dict[str, StateDefinition]) -> str:
    """Generate a YAML workflow string from the internal states dict.

    Output is round-trip safe: parseable back by yaml_parser.parse_workflow_yaml.
    """
    import yaml

    states_dict: dict = {}
    for name, sdef in graph.items():
        body: dict = {
            "handler_type": sdef.handler_type,
            "transitions": list(sdef.transitions),
            "input": sdef.input,
            "output": sdef.output,
        }
        # Preserve the AC-oriented schema fields; omit defaults for cleanliness
        # so plain states stay terse but gate/join/ac states round-trip intact.
        if sdef.gate:
            body["gate"] = sdef.gate
        if sdef.join_required:
            body["join_required"] = list(sdef.join_required)
        if sdef.acs:
            body["acs"] = [dict(ac) for ac in sdef.acs]
        states_dict[name] = body

    return yaml.dump(
        {"states": states_dict},
        default_flow_style=False,
        sort_keys=False,
    )


def _generate_mermaid(graph: dict[str, StateDefinition], current_state: str | None = None) -> str:
    """Generate a Mermaid stateDiagram-v2 from a workflow graph."""
    lines = ["stateDiagram-v2"]
    for name, sdef in graph.items():
        label = f"{name} ({sdef.handler_type})"
        lines.append(f"    {name} : {label}")
    for name, sdef in graph.items():
        if not sdef.transitions:
            lines.append(f"    {name} --> [*]")
        for target in sdef.transitions:
            lines.append(f"    {name} --> {target}")
    # Mark the first state as start
    first = next(iter(graph), None)
    if first:
        lines.append(f"    [*] --> {first}")
    return "\n".join(lines)


def update_workflow(
    workflow_yaml: str,
    reason: str,
    reset_to_state: str | None = None,
    meta_key: str = DEFAULT_META_KEY,
) -> dict:
    """Update the workflow definition, archiving the old version.

    Args:
        workflow_yaml: New workflow YAML definition.
        reason: Why the workflow is being updated (required).
        reset_to_state: If the current state is removed, reset to this state.
        meta_key: Registry member to operate on (default "artifact-flow").

    Returns:
        Success or error dict.
    """
    if not reason or not reason.strip():
        return make_error(
            REASON_REQUIRED,
            "A non-empty reason is required for update_workflow.",
            guidance="Provide a reason explaining why the workflow is changing.",
        )

    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    # Parse new YAML
    result = parse_workflow_yaml(workflow_yaml)
    if isinstance(result, dict) and "ok" in result and not result["ok"]:
        return result
    new_graph: dict[str, StateDefinition] = result  # type: ignore[assignment]

    # Permissive (NFR3/KD10): union the reshaped graph's handler types into
    # session caps so reshaping a member to use a new handler never refuses on
    # capability grounds. Capabilities are a descriptive record, not a gate.
    member_caps = {sd.handler_type for sd in new_graph.values() if sd.handler_type}
    wsf.meta.capabilities = sorted(set(wsf.meta.capabilities) | member_caps)

    # Validate new graph against (now-unioned) capabilities
    error = validate_graph(new_graph, wsf.meta.capabilities)
    if error is not None:
        return error

    current = entry.position.current_state
    current_preserved = current in new_graph

    # If current state removed and no reset_to_state provided, reject
    if not current_preserved and reset_to_state is None:
        surviving = list(new_graph.keys())
        return make_error(
            CURRENT_STATE_REMOVED,
            f"Current state '{current}' was removed from the new workflow.",
            details={
                "removed_state": current,
                "surviving_states": surviving,
            },
            guidance="Provide reset_to_state to specify where to move, or keep the current state in the new workflow.",
        )

    # If reset_to_state provided, validate it exists in new graph
    if reset_to_state is not None and reset_to_state not in new_graph:
        return make_error(
            STATE_NOT_FOUND,
            f"reset_to_state '{reset_to_state}' does not exist in the new workflow.",
            details={
                "state": reset_to_state,
                "known_states": list(new_graph.keys()),
            },
            guidance="Use a state name from the new workflow definition.",
        )

    # Archive old workflow to versions as YAML (versions array is file-global;
    # tag with meta_key so per-member version history is recoverable).
    old_version = entry.workflow.version
    wsf.versions.append({
        "meta_key": meta_key,
        "version": entry.workflow.version,
        "yaml": _generate_yaml(entry.workflow.states),
    })

    # Orphan output refs for removed states
    old_states = set(entry.workflow.states.keys())
    new_states = set(new_graph.keys())
    removed_states = old_states - new_states
    orphaned_outputs: dict[str, list] = {}
    for removed in removed_states:
        if removed in entry.position.outputs:
            orphaned_outputs[removed] = entry.position.outputs.pop(removed)
        # Orphan-clean the AC-oriented Position stores for removed states,
        # mirroring orphaned_outputs (DEFECT #3): joins, gate_evidence, acs.
        entry.position.joins.pop(removed, None)
        entry.position.gate_evidence.pop(removed, None)
        entry.position.acs.pop(removed, None)

    # Replace workflow
    new_version = old_version + 1
    entry.workflow = WorkflowState(version=new_version, states=new_graph)

    # Handle position
    previous_state = current
    if not current_preserved and reset_to_state is not None:
        entry.position.current_state = reset_to_state
        entry.position.blocked = None
        if reset_to_state not in entry.position.visited:
            entry.position.visited.append(reset_to_state)

    # Clean visited list — remove states no longer in workflow
    entry.position.visited = [s for s in entry.position.visited if s in new_graph]
    # Ensure current state is in visited
    cur = entry.position.current_state
    if cur not in entry.position.visited:
        entry.position.visited.append(cur)

    wsf.meta.status = _rollup_status(wsf)

    # Append history entry
    params: dict = {
        "meta_key": meta_key,
        "reason": reason,
        "old_version": old_version,
        "new_version": new_version,
        "added_states": sorted(new_states - old_states),
        "removed_states": sorted(removed_states),
    }
    if orphaned_outputs:
        params["orphaned_outputs"] = {k: v for k, v in orphaned_outputs.items()}
    if not current_preserved and reset_to_state is not None:
        params["reset_from"] = previous_state
        params["reset_to"] = reset_to_state

    wsf.history.append(
        make_entry(
            seq=next_seq(wsf.history),
            operation="update_workflow",
            params=params,
        )
    )

    _atomic_write(_state_path(), wsf.to_dict())

    return make_success({
        "old_version": old_version,
        "new_version": new_version,
        "current_state": entry.position.current_state,
        "added_states": sorted(new_states - old_states),
        "removed_states": sorted(removed_states),
        "orphaned_outputs": {k: v for k, v in orphaned_outputs.items()} if orphaned_outputs else {},
        "transitions": new_graph[entry.position.current_state].transitions,
    })


def resume(file_path: str) -> dict:
    """Resume a workflow from an existing state file.

    Loads the state file, validates its structure, sets it as the active
    session, and appends a resume history entry. This is the mechanism
    for crash recovery — the agent must explicitly pass the path.

    Args:
        file_path: Absolute path to an existing workflow-state.json.

    Returns:
        Success or error dict.
    """
    global _active_session_path

    if _active_session_path is not None:
        return make_error(
            ALREADY_INITIALIZED,
            "A session is already active.",
            details={"state_file": str(_active_session_path)},
            guidance="Cannot resume while a session is active. Each server instance manages one session.",
        )

    path = Path(file_path)
    if not path.exists():
        return make_error(
            NO_WORKFLOW,
            f"State file not found: {file_path}",
            details={"file_path": file_path},
            guidance="Provide the path returned by init's state_file field. Check that the file has not been deleted.",
        )

    try:
        with open(path) as f:
            data = json.load(f)
        wsf = WorkflowStateFile.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        return make_error(
            INVALID_STRUCTURE,
            f"Invalid state file: {e}",
            details={"file_path": file_path, "parse_error": str(e)},
            guidance="The file is corrupted or not a valid workflow-state.json. Re-initialize with init instead.",
        )

    _active_session_path = path

    # Append resume history entry
    wsf.history.append(
        make_entry(
            seq=next_seq(wsf.history),
            operation="resume",
            params={"file_path": file_path},
        )
    )
    _atomic_write(path, wsf.to_dict())

    # Report on the default member if present, else the first registered one.
    report_key = (
        DEFAULT_META_KEY if DEFAULT_META_KEY in wsf.workflows
        else (next(iter(wsf.workflows)) if wsf.workflows else None)
    )
    if report_key is not None:
        rep = wsf.workflows[report_key]
        current = rep.position.current_state
        current_def = rep.workflow.states.get(current)
        transitions = current_def.transitions if current_def else []
    else:
        current = ""
        transitions = []

    return make_success({
        "session_id": wsf.meta.session_id,
        "meta_key": report_key,
        "current_state": current,
        "transitions": transitions,
        "state_file": str(path),
        "history_count": len(wsf.history),
    })


def view_version(version: int, meta_key: str = DEFAULT_META_KEY) -> dict:
    """Return an archived workflow definition by version number.

    Args:
        version: The version number to retrieve.
        meta_key: Registry member whose version history to query
            (default "artifact-flow").

    Returns:
        Success or error dict.
    """
    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    # versions array is file-global; only match entries for this member.
    # Legacy entries (schema_version 1) carry no meta_key — treat them as
    # belonging to the default artifact-flow member.
    def _belongs(v: dict) -> bool:
        vk = v.get("meta_key", DEFAULT_META_KEY)
        return vk == meta_key

    for v in wsf.versions:
        if _belongs(v) and v.get("version") == version:
            return make_success({"version": v})

    # Also check current workflow — generate YAML on the fly
    if entry.workflow.version == version:
        return make_success({"version": {
            "meta_key": meta_key,
            "version": entry.workflow.version,
            "yaml": _generate_yaml(entry.workflow.states),
        }})

    return make_error(
        VERSION_NOT_FOUND,
        f"Version {version} not found.",
        details={
            "requested": version,
            "meta_key": meta_key,
            "current_version": entry.workflow.version,
            "archived_versions": [
                v.get("version") for v in wsf.versions if _belongs(v)
            ],
        },
        guidance="Use view_history to see version changes, or check the current workflow version.",
    )


def view_workflow(meta_key: str = DEFAULT_META_KEY) -> dict:
    """Return the current workflow graph with Mermaid diagram.

    Args:
        meta_key: Registry member to read (default "artifact-flow").

    Returns:
        Success or error dict.
    """
    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    graph = entry.workflow.states
    mermaid = _generate_mermaid(graph, entry.position.current_state)
    workflow_yaml = _generate_yaml(graph)

    return make_success({
        "meta_key": meta_key,
        "version": entry.workflow.version,
        "current_state": entry.position.current_state,
        "yaml": workflow_yaml,
        "mermaid": mermaid,
    })


def update_meta(
    title: str | None = None,
    description: str | None = None,
    exec_summary: str | None = None,
) -> dict:
    """Update workflow metadata fields.

    Only updates the fields that are provided (non-None).

    Args:
        title: New title for the workflow.
        description: New description for the workflow.
        exec_summary: New executive summary.

    Returns:
        Success or error dict.
    """
    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    updated: dict = {}
    if title is not None:
        wsf.meta.title = title
        updated["title"] = title
    if description is not None:
        wsf.meta.description = description
        updated["description"] = description
    if exec_summary is not None:
        wsf.meta.exec_summary = exec_summary
        updated["exec_summary"] = exec_summary

    if not updated:
        return make_success({"updated": {}, "message": "No fields to update."})

    wsf.history.append(
        make_entry(
            seq=next_seq(wsf.history),
            operation="update_meta",
            params={"updated_fields": updated},
        )
    )

    _atomic_write(_state_path(), wsf.to_dict())

    result_data: dict = {"updated": updated}

    # Soft validate exec_summary length
    if exec_summary is not None:
        word_count = len(exec_summary.split())
        if word_count > 500:
            result_data["warning"] = (
                f"exec_summary is {word_count} words, exceeding the recommended 500-word limit. "
                "Consider trimming to reference file paths instead of dumping content inline."
            )

    return make_success(result_data)


def list_sessions() -> dict:
    """Scan for all workflow sessions under the .task-tool/ directory.

    Does NOT require an active session.

    Returns:
        Success dict with a list of session summaries.
    """
    base = _base_dir() / STATE_DIR
    sessions: list[dict] = []

    if not base.exists():
        return make_success({"sessions": sessions})

    for state_file in base.rglob(STATE_FILE):
        try:
            with open(state_file) as f:
                data = json.load(f)
            wsf = WorkflowStateFile.from_dict(data)
        except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
            # Skip unreadable / malformed files
            continue

        meta = wsf.meta
        # Per-member status rollup + member summary array (KD1).
        members = []
        for mk, member in wsf.workflows.items():
            members.append({
                "meta_key": mk,
                "current_state": member.position.current_state,
                "status": _compute_status(member.position, member.workflow.states),
            })
        rollup = _rollup_status(wsf)
        # Session-level current_state: prefer the default member, else first.
        if DEFAULT_META_KEY in wsf.workflows:
            session_current = wsf.workflows[DEFAULT_META_KEY].position.current_state
        elif wsf.workflows:
            session_current = next(iter(wsf.workflows.values())).position.current_state
        else:
            session_current = ""

        sessions.append({
            "title": meta.title,
            "assignee": meta.assignee,
            "status": rollup,
            "exec_summary": meta.exec_summary,
            "current_state": session_current,
            "members": members,
            "state_file": str(state_file),
        })

    return make_success({"sessions": sessions})


def register_workflow(
    meta_key: str,
    workflow_yaml: str,
) -> dict:
    """Register an additional meta-keyed workflow member in the active session.

    The member's graph is validated in isolation — ``validate_graph`` runs over
    THIS member's states only, never the merged registry (KD2), so cross-member
    transition references cannot validate by construction.

    Args:
        meta_key: Registry key for the new member (must not already exist).
        workflow_yaml: Workflow YAML definition for this member.

    Returns:
        Success or error dict.
    """
    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a session before registering members.",
        )

    if meta_key in wsf.workflows:
        return make_error(
            META_KEY_EXISTS,
            f"A workflow is already registered under meta_key '{meta_key}'.",
            details={"meta_key": meta_key, "registered": list(wsf.workflows.keys())},
            guidance="Use a unique meta_key, or operate on the existing member.",
        )

    # Parse new YAML
    result = parse_workflow_yaml(workflow_yaml)
    if isinstance(result, dict) and "ok" in result and not result["ok"]:
        return result
    new_graph: dict[str, StateDefinition] = result  # type: ignore[assignment]

    # Permissive (NFR3/KD10): a member self-declares the handler types its graph
    # uses — union them into session caps so registering a powering aspect never
    # fails on capability grounds (e.g. a default-presenting session adding a
    # subagent lane). Capabilities are a descriptive record, not a gate.
    member_caps = {sd.handler_type for sd in new_graph.values() if sd.handler_type}
    wsf.meta.capabilities = sorted(set(wsf.meta.capabilities) | member_caps)

    # KD2: validate THIS member's isolated graph only — never the merged registry.
    error = validate_graph(new_graph, wsf.meta.capabilities)
    if error is not None:
        return error

    first_state = next(iter(new_graph))
    position = Position(
        current_state=first_state,
        visited=[first_state],
    )
    wsf.workflows[meta_key] = WorkflowEntry(
        workflow=WorkflowState(version=1, states=new_graph),
        position=position,
    )

    wsf.meta.status = _rollup_status(wsf)

    wsf.history.append(
        make_entry(
            seq=next_seq(wsf.history),
            operation="register_workflow",
            params={
                "meta_key": meta_key,
                "starting_state": first_state,
                "state_count": len(new_graph),
            },
        )
    )

    _atomic_write(_state_path(), wsf.to_dict())

    return make_success({
        "meta_key": meta_key,
        "current_state": first_state,
        "transitions": new_graph[first_state].transitions,
        "registered": list(wsf.workflows.keys()),
    })


# Threshold at which a recurring AC is surfaced for graduation to a verify rule.
AC_GRADUATION_THRESHOLD = 3

# Evidence flag a gate looks for before advance proceeds without a soft prompt.
REVIEW_EVIDENCE_FLAG = "has-review-subagent-checked"


def _convergence_states(graph: dict[str, StateDefinition]) -> set[str]:
    """Return the set of state names that declare a join (convergence states)."""
    return {name for name, sdef in graph.items() if sdef.join_required}


def _reaches(graph: dict[str, StateDefinition], src: str, dst: str) -> bool:
    """Return True if ``dst`` is forward-reachable from ``src`` (excluding the
    trivial src == dst case). Used for full reverse-reachability when deciding
    whether re-entering ``src`` begins a new pass through convergence ``dst``."""
    seen: set[str] = set()
    stack = list(graph.get(src).transitions) if graph.get(src) else []
    while stack:
        node = stack.pop()
        if node == dst:
            return True
        if node in seen:
            continue
        seen.add(node)
        sdef = graph.get(node)
        if sdef is not None:
            stack.extend(sdef.transitions)
    return False


def _move_to(entry: WorkflowEntry, target: str) -> None:
    """Move a member's position to ``target``, enforcing the join-reset invariant.

    The single shared move primitive for ALL force-move / advance sites
    (advance, reset_to, advance_without_evidence, override_transition). It does
    the three steps every move MUST do, in order:

      1. ``_reset_joins_on_reentry`` — clear a convergence state's per-pass
         accumulator on rework re-entry (KD3). Routing every move through here
         makes it structurally impossible for a future move op to skip the
         reset (the DEFECT #1 class).
      2. set ``current_state``.
      3. append to ``visited`` (idempotent).

    Site-distinct logic (blocked clearing, evidence checks, reason/history
    logging, status rollup) stays in each caller — only the common move is here.
    """
    _reset_joins_on_reentry(entry, target)
    entry.position.current_state = target
    if target not in entry.position.visited:
        entry.position.visited.append(target)


def _reset_joins_on_reentry(entry: WorkflowEntry, target: str) -> None:
    """Clear a convergence state's received set on rework re-entry (KD3).

    A new pass through a join must start from an empty accumulator. Re-entering
    the convergence state itself — or any predecessor that transitions into it —
    via a back-edge (i.e. the target is already visited, so this is a re-entry,
    not first arrival) clears that convergence state's ``received`` set. The
    accumulator is per-pass, not cumulative across cycles.
    """
    graph = entry.workflow.states
    position = entry.position
    convergence = _convergence_states(graph)
    if not convergence:
        return

    # Only a re-entry (target already visited) can be a rework back-edge;
    # a first-time arrival must not wipe an in-progress accumulation.
    is_reentry = target in position.visited
    if not is_reentry:
        return

    to_clear: set[str] = set()
    # Case 1: re-entering the convergence state directly.
    if target in convergence:
        to_clear.add(target)
    # Case 2: re-entering any state from which a convergence state is reachable
    # (full reverse-reachability, not just one-hop predecessors). A back-edge to
    # a state 2+ hops upstream of a convergence state still begins a new pass, so
    # that convergence state's per-pass accumulator must be cleared (KD3).
    for conv in convergence:
        if _reaches(graph, target, conv):
            to_clear.add(conv)

    for state_name in to_clear:
        rec = position.joins.get(state_name)
        if rec and rec.get("received"):
            rec["received"] = []


def record_branch_arrival(
    state: str,
    label: str,
    meta_key: str = DEFAULT_META_KEY,
) -> dict:
    """Record that a fan-out branch reported back to a convergence state (KD3).

    Adds ``label`` to ``Position.joins[state].received`` as a SET — the call is
    idempotent, so a retried or duplicated branch report cannot inflate the set
    past the true arrived branches. Records ARRIVAL (presence), NOT outcome: a
    failed branch still arrives; the converge_ready→rework decision is the
    lead's judgment from the branch's actual result, never stored here.

    Args:
        state: The convergence state the branch is reporting into.
        label: The branch identifier (must be declared in the state's
            ``join_required``).
        meta_key: Registry member to operate on (default "artifact-flow").

    Returns:
        Success or error dict.
    """
    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    sdef = entry.workflow.states.get(state)
    if sdef is None:
        return make_error(
            STATE_NOT_FOUND,
            f"State '{state}' does not exist in the workflow.",
            details={"state": state, "known_states": list(entry.workflow.states.keys())},
            guidance="Use a state name defined in the workflow YAML.",
        )

    required = list(sdef.join_required)
    if not required:
        return make_error(
            JOIN_STATE_REQUIRED,
            f"State '{state}' declares no join (no join_required).",
            details={"state": state},
            guidance="record_branch_arrival only applies to convergence states "
            "that declare join_required. Add join_required to the state, or "
            "record the arrival against the correct convergence state.",
        )

    if label not in required:
        return make_error(
            BRANCH_UNKNOWN,
            f"Branch '{label}' is not declared in '{state}' join_required.",
            details={"state": state, "label": label, "join_required": required},
            guidance="Use a branch label declared in the state's join_required, "
            "or fix the join_required declaration. Unknown labels are never "
            "silently counted.",
        )

    # Set semantics: idempotent add. Stored as a list for JSON serialization.
    rec = entry.position.joins.get(state)
    if not isinstance(rec, dict):
        rec = {"received": []}
        entry.position.joins[state] = rec
    received = list(rec.get("received", []))
    already = label in received
    if not already:
        received.append(label)
    rec["received"] = received

    missing = [b for b in required if b not in received]
    ready = not missing

    wsf.history.append(
        make_entry(
            seq=next_seq(wsf.history),
            operation="record_branch_arrival",
            params={
                "meta_key": meta_key,
                "state": state,
                "label": label,
                "idempotent_noop": already,
            },
        )
    )

    _atomic_write(_state_path(), wsf.to_dict())

    return make_success({
        "state": state,
        "label": label,
        "received": received,
        "required": required,
        "waiting_on": missing,
        "ready": ready,
    })


def view_join_status(meta_key: str = DEFAULT_META_KEY) -> dict:
    """Return per-convergence-state "blocked, waiting on X" join status (KD3).

    Computes ``required − received`` for every state that declares a join and
    names the missing branches. A focused per-state supplement to
    ``get_active_plan``'s ``waiting_joins`` field, not a required second call.

    Args:
        meta_key: Registry member to read (default "artifact-flow").

    Returns:
        Success or error dict.
    """
    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    joins: list[dict] = []
    for state_name, sdef in entry.workflow.states.items():
        required = list(sdef.join_required)
        if not required:
            continue
        rec = entry.position.joins.get(state_name, {}) or {}
        received = list(rec.get("received", []))
        missing = [b for b in required if b not in received]
        joins.append({
            "state": state_name,
            "required": required,
            "received": received,
            "waiting_on": missing,
            "ready": not missing,
            "status": "ready" if not missing
            else f"blocked, waiting on {', '.join(missing)}",
        })

    return make_success({"meta_key": meta_key, "joins": joins})


def record_review_evidence(
    meta_key: str = DEFAULT_META_KEY,
    gate_state: str = "",
) -> dict:
    """Record has-review-subagent-checked evidence for a gate state (KD5).

    Sets the evidence flag in ``Position.gate_evidence`` keyed by the GATE
    state's name, so a subsequent ``advance`` into that state proceeds without a
    soft recommendation. Uniform bar for every gate — no risk tiers.

    Args:
        meta_key: Registry member to operate on (default "artifact-flow").
        gate_state: The gate state name the review evidence applies to.

    Returns:
        Success or error dict.
    """
    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    sdef = entry.workflow.states.get(gate_state)
    if sdef is None:
        return make_error(
            STATE_NOT_FOUND,
            f"State '{gate_state}' does not exist in the workflow.",
            details={"state": gate_state, "known_states": list(entry.workflow.states.keys())},
            guidance="Use the gate state name defined in the workflow YAML.",
        )

    # Evidence records on ANY existing state. task-tool RECORDS, it does not
    # ENFORCE — `gate: true` is a convention marker for "human reviews here",
    # not a code gate. The "state must exist" check above is the only guard.
    rec = entry.position.gate_evidence.get(gate_state)
    if not isinstance(rec, dict):
        rec = {}
        entry.position.gate_evidence[gate_state] = rec
    rec[REVIEW_EVIDENCE_FLAG] = True
    rec["recorded_at"] = _now_iso()

    wsf.history.append(
        make_entry(
            seq=next_seq(wsf.history),
            operation="record_review_evidence",
            params={"meta_key": meta_key, "gate_state": gate_state},
        )
    )

    _atomic_write(_state_path(), wsf.to_dict())

    return make_success({
        "gate_state": gate_state,
        "gate_evidence": rec,
    })


def advance_without_evidence(
    target: str,
    reason: str,
    meta_key: str = DEFAULT_META_KEY,
) -> dict:
    """Advance into a gate state without review evidence, recording the reason.

    The recorded soft-gate audit path (KD5) — NOT a reuse of
    ``override_transition``. REQUIRES a LEGAL transition (rejects an off-graph
    target, unlike override's force-move) and records ONLY the single ``reason``
    in history, so the audit log distinguishes "advanced without review
    evidence" (routine, reason logged) from "force-moved off-graph"
    (override_transition, high concern).

    Args:
        target: Target state — must be a legal transition from the current state.
        reason: Why the lead is advancing without recorded review evidence
            (required, non-empty). Becomes the retrievable audit entry.
        meta_key: Registry member to operate on (default "artifact-flow").

    Returns:
        Success or error dict.
    """
    if not reason or not reason.strip():
        return make_error(
            REASON_REQUIRED,
            "A non-empty reason is required for advance_without_evidence.",
            guidance="Provide a reason explaining why you are advancing into "
            "the gate without recorded review evidence — it is logged for audit.",
        )

    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    if entry.position.blocked is not None:
        blocked = entry.position.blocked
        return make_error(
            POSITION_BLOCKED,
            f"Workflow is blocked — blocker: {blocked['blocker']}; unblock when: {blocked['unblock_condition']}; impact: {blocked['impact']}",
            details={
                "current_state": entry.position.current_state,
                "blocked": blocked,
            },
            guidance="Use reset_to or override_transition to recover.",
        )

    current = entry.position.current_state
    current_def = entry.workflow.states.get(current)
    if current_def is None:
        return make_error(
            NO_WORKFLOW,
            f"Current state '{current}' not found in workflow.",
            guidance="The state file may be corrupted.",
        )

    # task-tool RECORDS, it does not ENFORCE: the move is accepted into ANY
    # existing state as long as it is a LEGAL transition and a non-empty reason
    # is given (both KEPT below). `gate: true` is a convention marker, not a
    # precondition — no NOT_A_GATE refusal here.

    # Distinct from override_transition: a LEGAL transition is REQUIRED.
    if target not in current_def.transitions:
        return make_error(
            ILLEGAL_TRANSITION,
            f"Cannot transition from '{current}' to '{target}'.",
            details={
                "current_state": current,
                "target": target,
                "legal_transitions": current_def.transitions,
            },
            guidance=f"advance_without_evidence requires a legal transition. "
            f"Legal transitions from '{current}': {current_def.transitions}. "
            "To force-move off-graph use override_transition instead.",
        )

    # _move_to enforces the join-reset-on-re-entry invariant (KD3) for this site.
    _move_to(entry, target)

    wsf.meta.status = _rollup_status(wsf)

    wsf.history.append(
        make_entry(
            seq=next_seq(wsf.history),
            operation="advance_without_evidence",
            params={
                "meta_key": meta_key,
                "from": current,
                "to": target,
                "reason": reason,
            },
        )
    )

    _atomic_write(_state_path(), wsf.to_dict())

    target_def = entry.workflow.states[target]
    return make_success({
        "previous_state": current,
        "current_state": target,
        "transitions": target_def.transitions,
        "evidence_bypassed": True,
        "reason": reason,
    })


def _normalize_ac_identity(ac: dict) -> str:
    """Derive a stable identity key for an AC for dedup (KD7).

    Prefers an explicit ``id``/``rule``/``key`` reference (the registry stores
    ACs by reference to verify rule names / short AC keys, never rule bodies),
    falling back to the ``ac`` text. Identity is what dedup is keyed on so a
    re-failing AC bumps hit_count instead of appending a duplicate.
    """
    for k in ("id", "rule", "key"):
        v = ac.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    v = ac.get("ac")
    if isinstance(v, str) and v.strip():
        return v.strip()
    return ""


def accumulate_ac(
    meta_key: str,
    gate: str,
    ac: dict,
) -> dict:
    """Accumulate a failed acceptance criterion for a gate, deduped + bounded (KD7).

    On AC failure, dedups on AC identity: a re-failing AC bumps its ``hit_count``
    instead of appending a duplicate, so the list stays bounded across rework
    loops. Prior ACs are preserved and the accumulated set is re-surfaced on the
    next pass through the gate (via ``get_active_plan`` / this member's
    ``Position.acs[gate]``). AC entries reference verify rule names / short AC
    keys, NOT copied rule bodies.

    Args:
        meta_key: Registry member to operate on.
        gate: The gate state the AC belongs to.
        ac: The acceptance criterion dict — references a verify rule name /
            short AC key (e.g. ``{"id": "diagram-present", "ac": "..."}``).

    Returns:
        Success or error dict.
    """
    wsf = _load_state()
    if wsf is None:
        return make_error(
            NO_WORKFLOW,
            "No workflow initialized.",
            guidance="Call init first to create a workflow.",
        )

    entry, err = _resolve_member(wsf, meta_key)
    if err is not None:
        return err

    sdef = entry.workflow.states.get(gate)
    if sdef is None:
        return make_error(
            STATE_NOT_FOUND,
            f"State '{gate}' does not exist in the workflow.",
            details={"state": gate, "known_states": list(entry.workflow.states.keys())},
            guidance="Use a state name defined in the workflow YAML.",
        )

    # ACs attach to ANY existing state — `gate: true` is a convention marker for
    # a human-review checkpoint, NOT a precondition for accumulating an AC.
    # task-tool RECORDS, it does not ENFORCE. The "state must exist" check above
    # is the only guard.

    identity = _normalize_ac_identity(ac)

    # Provenance: a TRUTHFUL origin tag the lead sets per AC — "user" (a
    # user-given requirement) vs "ai" (an AI-inferred addition). Default to "ai"
    # when absent: an unattributed AC is treated as the lead-AI's own addition.
    # A later review agent reads origin to challenge each AC through a different
    # lens; that lens logic is PROMPT-LAYER, we only store + surface the tag.
    origin = ac.get("origin")
    if origin not in ("user", "ai"):
        origin = "ai"

    ac_list = entry.position.acs.get(gate)
    if not isinstance(ac_list, list):
        ac_list = []
        entry.position.acs[gate] = ac_list

    note: str | None = None

    if not identity:
        # Graceful fallback: an AC with no stable identity (no id/rule/key/ac)
        # cannot be deduped, so we append it UNCONDITIONALLY (skip dedup) rather
        # than refuse. Recording state is the job; dedup is a convenience that
        # only applies to identity-bearing ACs.
        record = dict(ac)
        record["origin"] = origin
        record.setdefault("hit_count", 1)
        ac_list.append(record)
        deduped = False
        note = (
            "AC has no stable identity (id/rule/key/ac); appended without dedup. "
            "Reference a /verify rule name or short AC key to enable dedup."
        )
    else:
        # Dedup on AC identity: bump hit_count instead of appending a duplicate.
        existing = None
        for item in ac_list:
            if _normalize_ac_identity(item) == identity:
                existing = item
                break

        if existing is not None:
            existing["hit_count"] = existing.get("hit_count", 1) + 1
            deduped = True
            record = existing
        else:
            record = dict(ac)
            record["origin"] = origin
            record.setdefault("hit_count", 1)
            ac_list.append(record)
            deduped = False

    hit_count = record.get("hit_count", 1)
    graduate = hit_count >= AC_GRADUATION_THRESHOLD

    wsf.history.append(
        make_entry(
            seq=next_seq(wsf.history),
            operation="accumulate_ac",
            params={
                "meta_key": meta_key,
                "gate": gate,
                "ac_identity": identity,
                "origin": record.get("origin", origin),
                "deduped": deduped,
                "hit_count": hit_count,
            },
        )
    )

    _atomic_write(_state_path(), wsf.to_dict())

    result = {
        "gate": gate,
        "ac": record,
        "origin": record.get("origin", origin),
        "deduped": deduped,
        "hit_count": hit_count,
        "graduate": graduate,
        "total_acs": len(ac_list),
    }
    if note is not None:
        result["note"] = note
    return make_success(result)


def _member_plan(entry: WorkflowEntry) -> dict:
    """Build the get_active_plan view for one registry member.

    Pure read over the member's persisted ``joins`` / ``gate_evidence`` / ``acs``
    stores. Empty stores (no join/evidence/AC data yet) yield empty lists, so the
    shape is stable regardless of which downstream phases have populated them.
    """
    graph = entry.workflow.states
    position = entry.position

    # waiting_joins: declared join states whose received set is incomplete.
    waiting_joins: list[dict] = []
    ready_join_states: set[str] = set()
    for state_name, sdef in graph.items():
        required = list(sdef.join_required)
        if not required:
            continue
        join_rec = position.joins.get(state_name, {}) or {}
        received = set(join_rec.get("received", []))
        missing = [b for b in required if b not in received]
        if missing:
            waiting_joins.append({"state": state_name, "waiting_on": missing})
        else:
            ready_join_states.add(state_name)

    # ready_gates: join-complete states, plus ANY state whose review evidence is
    # satisfied — surfaced REGARDLESS of `gate: true`. Evidence attaches to any
    # state (task-tool records, it does not enforce); `gate: true` only labels a
    # state as a review checkpoint, it does NOT decide whether evidence is read.
    ready_gates: list[str] = list(ready_join_states)
    for state_name, evidence in (position.gate_evidence or {}).items():
        if not isinstance(evidence, dict):
            continue
        if evidence.get("has-review-subagent-checked"):
            if state_name not in ready_gates:
                ready_gates.append(state_name)

    # open_acs: accumulated ACs with hit_count + graduation flag (KD7). ACs
    # surface REGARDLESS of whether their carrying state is `gate: true` —
    # `gate: true` only labels the state as a review checkpoint (the `gate` flag
    # on each entry), it does NOT decide whether ACs are read. graduation_prompts:
    # mechanical trigger — when an AC's hit_count crosses the threshold, surface a
    # "graduate to verify rule" prompt. Detection is mechanized here; authoring
    # the rule stays a lead/flag-imp step.
    open_acs: list[dict] = []
    graduation_prompts: list[dict] = []
    for gate_name, ac_list in (position.acs or {}).items():
        carrier = graph.get(gate_name)
        is_gate = bool(carrier.gate) if carrier is not None else False
        for ac in ac_list:
            hit_count = ac.get("hit_count", 1)
            ac_ref = ac.get("id", ac.get("rule", ac.get("key", ac.get("ac", ""))))
            ac_origin = ac.get("origin", "ai")
            graduate = hit_count >= AC_GRADUATION_THRESHOLD
            open_acs.append({
                "gate": is_gate,
                "state": gate_name,
                "ac": ac_ref,
                "origin": ac_origin,
                "hit_count": hit_count,
                "graduate": graduate,
            })
            if graduate:
                graduation_prompts.append({
                    "state": gate_name,
                    "ac": ac_ref,
                    "hit_count": hit_count,
                    "prompt": (
                        f"AC '{ac_ref}' has failed {hit_count} times at state "
                        f"'{gate_name}' (threshold {AC_GRADUATION_THRESHOLD}). "
                        "Consider graduating it to a durable /verify rule via "
                        "/flag-imp."
                    ),
                })

    return {
        "current_state": position.current_state,
        "ready_gates": ready_gates,
        "waiting_joins": waiting_joins,
        "open_acs": open_acs,
        "graduation_prompts": graduation_prompts,
    }


def get_active_plan() -> dict:
    """Return the full registry of the session already attached to this process.

    Session-scoped pure READ (KD8): no ``.task-tool/`` scan, no recency
    resolution, no session latching. Returns every registry member's plan view
    plus the session status rollup in one call (MR1). Session selection stays
    with ``init`` / ``resume`` — this never changes the attached session.

    No-session contract (NFR1): when nothing is attached, returns a typed
    success ``{ok: true, active_plan: null, attached: false}`` with guidance
    pointing to ``init`` (new) or ``list_sessions`` + ``resume`` (existing) —
    NOT an error.

    Returns:
        Success dict.
    """
    wsf = _load_state()
    if wsf is None:
        return {
            "ok": True,
            "active_plan": None,
            "attached": False,
            "guidance": (
                "No workflow session is attached. Call init to start a new "
                "session, or list_sessions then resume(path) to attach an "
                "existing one."
            ),
        }

    members = {mk: _member_plan(entry) for mk, entry in wsf.workflows.items()}

    return {
        "ok": True,
        "attached": True,
        "active_plan": {
            "session_id": wsf.meta.session_id,
            "status": _rollup_status(wsf),
            "members": members,
        },
    }
