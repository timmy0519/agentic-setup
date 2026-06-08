"""Data models for the task-tool workflow state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Meta:
    schema_version: int
    created_at: str  # ISO 8601
    session_id: str  # UUID4
    capabilities: list[str]
    title: str = ""
    description: str = ""
    assignee: str = ""
    status: str = "active"  # auto-derived: "active", "blocked", "done"
    exec_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "session_id": self.session_id,
            "capabilities": list(self.capabilities),
            "title": self.title,
            "description": self.description,
            "assignee": self.assignee,
            "status": self.status,
            "exec_summary": self.exec_summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Meta:
        return cls(
            schema_version=d["schema_version"],
            created_at=d["created_at"],
            session_id=d["session_id"],
            capabilities=list(d["capabilities"]),
            title=d.get("title", ""),
            description=d.get("description", ""),
            assignee=d.get("assignee", ""),
            status=d.get("status", "active"),
            exec_summary=d.get("exec_summary", ""),
        )


@dataclass
class StateDefinition:
    handler_type: str
    transitions: list[str]
    input: str = ""
    output: str = ""
    gate: bool = False
    acs: list[dict] = field(default_factory=list)
    join_required: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "handler_type": self.handler_type,
            "transitions": list(self.transitions),
            "input": self.input,
            "output": self.output,
            "gate": self.gate,
            "acs": list(self.acs),
            "join_required": list(self.join_required),
        }

    @classmethod
    def from_dict(cls, d: dict) -> StateDefinition:
        return cls(
            handler_type=d["handler_type"],
            transitions=list(d["transitions"]),
            input=d.get("input", ""),
            output=d.get("output", ""),
            gate=d.get("gate", False),
            acs=list(d.get("acs", [])),
            join_required=list(d.get("join_required", [])),
        )


@dataclass
class WorkflowState:
    version: int
    states: dict[str, StateDefinition]

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "states": {k: v.to_dict() for k, v in self.states.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorkflowState:
        return cls(
            version=d["version"],
            states={k: StateDefinition.from_dict(v) for k, v in d["states"].items()},
        )


@dataclass
class Position:
    current_state: str
    blocked: dict | None = None
    outputs: dict[str, list] = field(default_factory=dict)
    visited: list[str] = field(default_factory=list)
    joins: dict = field(default_factory=dict)
    gate_evidence: dict = field(default_factory=dict)
    acs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "current_state": self.current_state,
            "blocked": self.blocked,
            "outputs": dict(self.outputs),
            "visited": list(self.visited),
            "joins": dict(self.joins),
            "gate_evidence": dict(self.gate_evidence),
            "acs": dict(self.acs),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Position:
        return cls(
            current_state=d["current_state"],
            blocked=d.get("blocked"),
            outputs=d.get("outputs", {}),
            visited=list(d.get("visited", [])),
            joins=d.get("joins", {}),
            gate_evidence=d.get("gate_evidence", {}),
            acs=d.get("acs", {}),
        )


@dataclass
class HistoryEntry:
    seq: int
    timestamp: str  # ISO 8601
    operation: str
    params: dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "operation": self.operation,
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, d: dict) -> HistoryEntry:
        return cls(
            seq=d["seq"],
            timestamp=d["timestamp"],
            operation=d["operation"],
            params=d.get("params", {}),
        )


@dataclass
class WorkflowEntry:
    workflow: WorkflowState
    position: Position

    def to_dict(self) -> dict:
        return {
            "workflow": self.workflow.to_dict(),
            "position": self.position.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorkflowEntry:
        return cls(
            workflow=WorkflowState.from_dict(d["workflow"]),
            position=Position.from_dict(d["position"]),
        )


@dataclass
class WorkflowStateFile:
    meta: Meta
    workflows: dict[str, WorkflowEntry] = field(default_factory=dict)
    history: list[HistoryEntry] = field(default_factory=list)
    versions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "meta": self.meta.to_dict(),
            "workflows": {k: v.to_dict() for k, v in self.workflows.items()},
            "history": [h.to_dict() for h in self.history],
            "versions": list(self.versions),
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorkflowStateFile:
        meta = Meta.from_dict(d["meta"])
        if "workflows" in d:
            workflows = {
                k: WorkflowEntry.from_dict(v) for k, v in d["workflows"].items()
            }
        elif "workflow" in d:
            # LEGACY (schema_version 1): single .workflow/.position pair.
            workflows = {
                "artifact-flow": WorkflowEntry(
                    workflow=WorkflowState.from_dict(d["workflow"]),
                    position=Position.from_dict(d["position"]),
                )
            }
            if meta.schema_version == 1:
                meta.schema_version = 2
        else:
            workflows = {}
        return cls(
            meta=meta,
            workflows=workflows,
            history=[HistoryEntry.from_dict(h) for h in d.get("history", [])],
            versions=d.get("versions", []),
        )
