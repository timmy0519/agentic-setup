"""Graph structure validator for workflow definitions."""

from __future__ import annotations

from .errors import (
    CAPABILITY_MISMATCH,
    INVALID_STRUCTURE,
    make_error,
)
from .models import StateDefinition


def validate_graph(
    graph: dict[str, StateDefinition],
    capabilities: list[str],
) -> dict | None:
    """Validate a parsed workflow graph.

    Returns:
        None on success, or an error dict on failure.
    """
    # 1. At least one state exists
    if not graph:
        return make_error(
            INVALID_STRUCTURE,
            "Workflow must contain at least one state.",
            guidance="Add at least one state to the 'states' mapping.",
        )

    # 2. Every transition target names an existing state
    for state_name, state_def in graph.items():
        for target in state_def.transitions:
            if target not in graph:
                return make_error(
                    INVALID_STRUCTURE,
                    f"State '{state_name}' has transition to unknown state '{target}'.",
                    details={"state": state_name, "target": target},
                    guidance=f"Define state '{target}' or remove the transition.",
                )

    # 3. join_required labels are non-empty strings (branch identifiers, KD3).
    #    These are branch labels matched at runtime against record_branch_arrival
    #    — NOT necessarily state names — so they are validated for shape only,
    #    never resolved against the member graph. Validation stays per-member:
    #    a member's transition targets and labels never reach beyond its own
    #    graph, so cross-workflow references remain structurally impossible (C2).
    for state_name, state_def in graph.items():
        for label in state_def.join_required:
            if not isinstance(label, str) or not label.strip():
                return make_error(
                    INVALID_STRUCTURE,
                    f"State '{state_name}' has an empty or non-string "
                    f"join_required label.",
                    details={"state": state_name},
                    guidance="Each join_required entry must be a non-empty branch label string.",
                )

    # 4. Cycles must have at least one exit
    #    Find all SCCs; for each SCC with >1 node (or self-loop), verify
    #    at least one member has a transition outside the SCC.
    sccs = _tarjan_scc(graph)
    for scc in sccs:
        scc_set = set(scc)

        # Check if this is actually a cycle (self-loop or multi-node SCC)
        is_cycle = len(scc) > 1
        if len(scc) == 1:
            node = scc[0]
            is_cycle = node in graph[node].transitions

        if not is_cycle:
            continue

        has_exit = False
        for node in scc:
            for target in graph[node].transitions:
                if target not in scc_set:
                    has_exit = True
                    break
            if has_exit:
                break

        if not has_exit:
            return make_error(
                INVALID_STRUCTURE,
                f"Cycle {sorted(scc)} has no exit transition.",
                details={"cycle": sorted(scc)},
                guidance="Add a transition from at least one state in the cycle to a state outside it.",
            )

    # 5. Every handler_type is in the declared capabilities list
    caps_set = set(capabilities)
    for state_name, state_def in graph.items():
        if state_def.handler_type not in caps_set:
            return make_error(
                CAPABILITY_MISMATCH,
                f"State '{state_name}' uses handler_type '{state_def.handler_type}' "
                f"which is not in declared capabilities {capabilities}.",
                details={
                    "state": state_name,
                    "handler_type": state_def.handler_type,
                    "capabilities": capabilities,
                },
                guidance=f"Add '{state_def.handler_type}' to capabilities or change the handler_type.",
            )

    return None


def _tarjan_scc(graph: dict[str, StateDefinition]) -> list[list[str]]:
    """Tarjan's algorithm to find strongly connected components."""
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    result: list[list[str]] = []

    def strongconnect(node: str) -> None:
        index[node] = index_counter[0]
        lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack.add(node)

        for target in graph[node].transitions:
            if target not in index:
                strongconnect(target)
                lowlink[node] = min(lowlink[node], lowlink[target])
            elif target in on_stack:
                lowlink[node] = min(lowlink[node], index[target])

        if lowlink[node] == index[node]:
            component: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == node:
                    break
            result.append(component)

    for node in graph:
        if node not in index:
            strongconnect(node)

    return result
