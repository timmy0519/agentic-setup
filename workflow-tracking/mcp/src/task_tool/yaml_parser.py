"""YAML parser for workflow definitions."""

from __future__ import annotations

import yaml

from .errors import INVALID_STRUCTURE, make_error
from .models import StateDefinition


# Fields allowed at each level
_ALLOWED_TOP_KEYS = {"states"}
_ALLOWED_STATE_KEYS = {
    "handler_type",
    "transitions",
    "input",
    "output",
    "gate",
    "acs",
    "join_required",
}


def parse_workflow_yaml(yaml_str: str) -> dict | dict[str, StateDefinition]:
    """Parse a YAML workflow string into a dict of state name -> StateDefinition.

    ``input``/``output`` are OPTIONAL (default empty string) — a minimal stub
    state parses. Non-empty, descriptive ``input``/``output`` are RECOMMENDED for
    a useful plan view but are not enforced: task-tool records state, it does not
    police authoring quality.

    Returns:
        On success: dict[str, StateDefinition]
        On failure: error dict ({"ok": false, ...})
    """
    try:
        raw = yaml.safe_load(yaml_str)
    except yaml.YAMLError as exc:
        return make_error(
            INVALID_STRUCTURE,
            "Failed to parse YAML.",
            details={"parse_error": str(exc)},
            guidance="Ensure the workflow_yaml is valid YAML.",
        )

    if not isinstance(raw, dict):
        return make_error(
            INVALID_STRUCTURE,
            "Top-level YAML must be a mapping.",
            guidance="The YAML should have a top-level 'states' key.",
        )

    # Reject unknown top-level keys
    unknown_top = set(raw.keys()) - _ALLOWED_TOP_KEYS
    if unknown_top:
        return make_error(
            INVALID_STRUCTURE,
            f"Unknown top-level keys: {sorted(unknown_top)}",
            details={"unknown_keys": sorted(unknown_top)},
            guidance=f"Allowed top-level keys: {sorted(_ALLOWED_TOP_KEYS)}",
        )

    if "states" not in raw:
        return make_error(
            INVALID_STRUCTURE,
            "Missing required key 'states'.",
            guidance="The YAML must contain a 'states' mapping.",
        )

    states_raw = raw["states"]
    if not isinstance(states_raw, dict) or len(states_raw) == 0:
        return make_error(
            INVALID_STRUCTURE,
            "'states' must be a non-empty mapping.",
            guidance="Define at least one state under 'states'.",
        )

    graph: dict[str, StateDefinition] = {}

    for state_name, state_body in states_raw.items():
        if not isinstance(state_name, str):
            return make_error(
                INVALID_STRUCTURE,
                f"State name must be a string, got: {type(state_name).__name__}",
            )

        if not isinstance(state_body, dict):
            return make_error(
                INVALID_STRUCTURE,
                f"State '{state_name}' body must be a mapping.",
            )

        unknown_state = set(state_body.keys()) - _ALLOWED_STATE_KEYS
        if unknown_state:
            return make_error(
                INVALID_STRUCTURE,
                f"State '{state_name}' has unknown keys: {sorted(unknown_state)}",
                details={"state": state_name, "unknown_keys": sorted(unknown_state)},
                guidance=f"Allowed state keys: {sorted(_ALLOWED_STATE_KEYS)}",
            )

        if "handler_type" not in state_body:
            return make_error(
                INVALID_STRUCTURE,
                f"State '{state_name}' missing required key 'handler_type'.",
            )

        if "transitions" not in state_body:
            return make_error(
                INVALID_STRUCTURE,
                f"State '{state_name}' missing required key 'transitions'.",
            )

        handler_type = state_body["handler_type"]
        transitions = state_body["transitions"]
        # input/output are OPTIONAL (default empty string). A minimal stub state
        # must parse — task-tool RECORDS, it does not enforce authoring quality.
        # Non-empty descriptions are recommended but not required; see docstring.
        input_desc = state_body.get("input", "")
        output_desc = state_body.get("output", "")

        if not isinstance(handler_type, str):
            return make_error(
                INVALID_STRUCTURE,
                f"State '{state_name}' handler_type must be a string.",
            )

        if not isinstance(transitions, list):
            return make_error(
                INVALID_STRUCTURE,
                f"State '{state_name}' transitions must be a list.",
            )

        for t in transitions:
            if not isinstance(t, str):
                return make_error(
                    INVALID_STRUCTURE,
                    f"State '{state_name}' transition targets must be strings.",
                )

        if not isinstance(input_desc, str):
            return make_error(
                INVALID_STRUCTURE,
                f"State '{state_name}' input must be a string.",
            )

        if not isinstance(output_desc, str):
            return make_error(
                INVALID_STRUCTURE,
                f"State '{state_name}' output must be a string.",
            )

        # Optional fields (default-empty so legacy/minimal definitions parse).
        gate = state_body.get("gate", False)
        if not isinstance(gate, bool):
            return make_error(
                INVALID_STRUCTURE,
                f"State '{state_name}' gate must be a boolean.",
            )

        acs = state_body.get("acs", [])
        if not isinstance(acs, list):
            return make_error(
                INVALID_STRUCTURE,
                f"State '{state_name}' acs must be a list.",
            )
        for ac in acs:
            if not isinstance(ac, dict):
                return make_error(
                    INVALID_STRUCTURE,
                    f"State '{state_name}' acs entries must be mappings.",
                )

        join_required = state_body.get("join_required", [])
        if not isinstance(join_required, list):
            return make_error(
                INVALID_STRUCTURE,
                f"State '{state_name}' join_required must be a list.",
            )
        for label in join_required:
            if not isinstance(label, str):
                return make_error(
                    INVALID_STRUCTURE,
                    f"State '{state_name}' join_required labels must be strings.",
                )

        graph[state_name] = StateDefinition(
            handler_type=handler_type,
            transitions=transitions,
            input=input_desc,
            output=output_desc,
            gate=gate,
            acs=acs,
            join_required=join_required,
        )

    return graph
