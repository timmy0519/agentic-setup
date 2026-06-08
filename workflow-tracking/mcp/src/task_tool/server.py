"""MCP server entry point for the task-tool."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .errors import make_error, INVALID_STRUCTURE
from .models import StateDefinition
from .yaml_parser import parse_workflow_yaml
from .validator import validate_graph
from . import state as state_mod

mcp = FastMCP("task-tool")

# ── Tool-naming conventions (so a cold lead can route by prefix alone) ──
# get_*   = PRIMARY read. `get_active_plan` is THE default "where do things
#           stand" call — invoke it first each turn; it returns everything.
# view_*  = NARROW supplement / static lookup. Reach for one only when you
#           need a single slice (one scalar, the static graph, the audit log).
#           Never a required second call after get_active_plan.
# advance = DEFAULT mover. The fallbacks escalate in ceremony:
#           advance → advance_without_evidence (legal edge, skip gate review)
#                   → reset_to (rework / recover a blocked position)
#                   → override_transition (off-graph force; last resort).
# record_*/accumulate_ac = attach data to a state (output, review evidence,
#           branch arrival, AC). register_workflow = create a member;
#           update_workflow = modify an existing member's graph.
# The tool RECORDS, it does not ENFORCE (NFR3/KD10): it accepts any move whose
# structural minimums hold and only ever SURFACES soft recommendations.


# Built-in default PRESENTING aspect (MR3): the universal "general report"
# skeleton — do work, pull the user in at one review gate, finish. Used when a
# caller inits without authoring a presenting graph. It is the executable,
# self-contained baseline (no skill required); /artifact-flow generates richer,
# task-class-matched presenting aspects. Kept deliberately minimal — one gate —
# so it nudges toward an intentional choice rather than prescribing structure.
DEFAULT_PRESENTING_GRAPH_YAML = """\
states:
  build:
    handler_type: self
    transitions: [review]
    output: "Deliverable(s) for this task"
  review:
    handler_type: self
    gate: true
    transitions: [build, done]
    input: "Deliverable ready for review — surface to the user if appropriate"
    output: "Review verdict (approve / request changes)"
  done:
    handler_type: self
    transitions: []
    input: "Approved deliverable"
"""


@mcp.tool()
def init(
    capabilities: list[str] | None = None,
    workflow_yaml: str | None = None,
    resume_from: str | None = None,
    title: str = "",
    description: str = "",
    assignee: str = "",
    meta_key: str = "artifact-flow",
) -> dict:
    """Initialize a workflow or resume from an existing state file.

    ## A session = one workflow with TWO aspects (MR3)

    A session is the parent. It composes:
    - a PRESENTING aspect (this is the default member, meta_key="artifact-flow"):
      WHEN/how the user reviews, and which gates persist to disk WITH their ACs
      even if the user never looks. This is what pulls the human in at the right
      moments.
    - one or more POWERING aspects (added later via register_workflow): HOW the
      work actually gets done — explore / build / verify lanes.

    The PRESENTING aspect is MANDATORY — every session must declare how the user
    reviews. You have three ways, in order of preference:
      1. Read and apply the /artifact-flow skill (ships with the verify-suite
         plugin) — RECOMMENDED, because the presenting aspect is a core concept
         and /artifact-flow picks a structure matched to your task class. Not
         required: option 3 keeps workflow-tracking usable standalone.
      2. Author your own workflow_yaml (the design guide below).
      3. Omit workflow_yaml entirely — the tool falls back to a built-in
         general-report skeleton (build -> user-review gate -> done) and returns
         a recommendation reminding you this was a fallback, not a choice.
    Picking the minimal default is valid; doing it silently is the thing to
    avoid — the choice should be intentional and visible in the record.

    ## New workflow

    Provide capabilities + workflow_yaml + title + description + assignee (or
    omit workflow_yaml for the default presenting aspect).

    - title: Short descriptive title, e.g. 'Research MCP session patterns'
    - description: Brief scope description for this workflow
    - assignee: Owner identifier, convention: <type>-<topic>-<role>,
      e.g. 'research-mcp-patterns-lead', 'impl-auth-middleware-dev'

    ## Resume

    Provide resume_from (path to existing workflow-state.json).
    Loads and validates the file, continues from persisted position.
    This is a conscious decision — no automatic discovery.

    ## Workflow YAML design guide

    A workflow externalizes your plan into a trackable, auditable state machine.

    ### State-machine layer vs native task-list layer (MR2)

    This registry holds ONLY high-level workflow items: states, gates, and
    accumulated ACs. It is the active-plan abstraction — the gates a lead cares
    about. It does NOT hold step-level detail or inter-agent coordination chatter.
    Keep detail and coordination in your native task list (TaskCreate/TaskUpdate);
    keep gate-shaped, auditable, resumable items here. Two layers, one boundary:
    registry = high-level item + gate/AC contract; native list = detail + handoff.

    ### gate / acs / join_required — the marker + accumulation keys

    task-tool RECORDS state; it does NOT enforce it. Governance lives in the lead
    prompt + hooks, not in tool refusals.

    - gate (bool): a CONVENTION marker for a human-review checkpoint — NOT a code
      gate. It does not block anything. Advancing INTO a gate-marked state without
      recorded review evidence returns a SOFT recommendation (typed success, never
      a refusal) routing you to record_review_evidence(meta_key, gate_state) then
      retry advance, OR advance_without_evidence(target, reason) to proceed with
      the reason logged. Only gate-marked states emit this advisory nudge; it is
      never a block.
    - join_required (list[str]): marks a convergence state where N fan-out
      branches must report back. Each branch calls record_branch_arrival(state,
      label); the join is "ready" only once every declared label has arrived.
      Arrival records PRESENCE, not outcome — a failed branch still arrives; the
      converge→rework decision is your judgment from the branch's actual result.
      view_join_status shows per-state "blocked, waiting on X". Re-entering a
      convergence state (or its predecessor) via a back-edge clears that state's
      received set — accumulation is per-pass, not cumulative across rework loops.
    - acs (accumulated) + review-evidence: these attach to ANY state and surface
      in get_active_plan REGARDLESS of gate. On AC failure call accumulate_ac(
      meta_key, state, ac). Failed ACs accumulate deduped + bounded — a re-failing
      AC bumps its hit_count instead of duplicating — and re-surface on the next
      pass. When hit_count crosses the graduation threshold, get_active_plan
      surfaces a prompt to graduate it to a durable /verify rule via /flag-imp.
      An AC is a SHARED REFERENCE: put a /verify rule name in id / rule / key and
      duplicate that same pointer to a worker's task so worker and lead share one
      standard. AC entries reference verify rule names / short AC keys, NEVER
      copied rule bodies. Tag origin: "user" | "ai" on each AC for auditable
      provenance — "user" = a user-given requirement, "ai" = an AI-inferred
      addition (the default when origin is omitted). A later review agent reads
      origin to challenge each AC through a different lens by provenance.

    The dynamic Workflow READS this plan (get_active_plan) to know where things
    stand; the lead WRITES it (advance / record_* / accumulate_ac). Read-side and
    write-side are separated by design (KD9).

    ### Authoring ACs and gates (NFR2)

    - Write each AC as an OUTCOME CONTRACT a Workflow or subagent can honor —
      "diagram present and every requirement traced", not "run verify-design".
      The AC states the observable outcome, not the tool invocation.
    - Place gates at EXECUTOR BOUNDARIES — the points where work crosses from one
      handler to the next (writer → reviewer, branch fan-out → convergence). A
      gate mid-handler with no boundary to guard is noise.
    - Because the Workflow reads the plan and the lead writes it, an AC that only
      the lead's private context can evaluate is mis-authored; phrase it so the
      reading party can check it against the artifact.

    ### handler_type — who handles each state

    Declares what kind of actor runs this state. Validated against your
    capabilities at init — don't declare what you can't provision.

    - self: you handle it directly
    - subagent: you spawn a focused worker via Agent tool
    - peer: a teammate on your team handles it
    - agent: a separate agent process (e.g., tmux pane)
    - agent_team: a multi-agent team spawned for this state
    - human_user: requires user input or approval

    ### input / output — the contract per state

    Each state MAY declare what it needs to begin (input) and what it must
    produce before advancing (output). Both are OPTIONAL — a minimal stub state
    parses with neither — but non-empty, descriptive input/output are strongly
    RECOMMENDED so a replacement agent knows exactly what to deliver without
    reading full history. Reference file paths when possible, not inline content.

    Example:
      search:
        input: "2-3 focused queries from plan state"
        output: "Consolidated results with sources, saved to search-results.md"

    ### transitions — legal next states

    Define which states can follow this one. The AI must explicitly call
    advance(target) — the tool never auto-advances.

    Patterns:

    Linear (simple pipeline):
      plan → search → draft → done
      plan:
        transitions: [search]
      search:
        transitions: [draft]

    Back-edge (rework loop):
      review can reject back to draft or approve to done
      review:
        transitions: [draft, done]

    Branching (conditional next step):
      after research, either draft findings or revisit the plan
      research:
        transitions: [draft, plan]

    Self-loop (iterate in place):
      draft can revise itself before sending to review
      draft:
        transitions: [draft, review]

    Terminal (workflow complete):
      done:
        transitions: []

    ### Full example

    states:
      plan:
        handler_type: self
        transitions: [search]
        input: "Research topic and scope from init description"
        output: "2-3 focused search queries with rationale"
      search:
        handler_type: subagent
        transitions: [draft, plan]
        input: "Search queries from plan state"
        output: "Consolidated results with sources"
      draft:
        handler_type: self
        transitions: [draft, review]
        input: "Search results from search state"
        output: "Research note at Research/<topic>.md"
      review:
        handler_type: peer
        transitions: [draft, done]
        input: "Draft research note for quality review"
        output: "Review verdict: approve or list issues"
      done:
        handler_type: self
        transitions: []
        input: "Approved research note"
        output: "Final deliverable path"
    """
    if resume_from is not None:
        return state_mod.resume(resume_from)

    # MANDATORY presenting aspect (MR3): every session declares HOW the user
    # reviews. If the caller authors no graph, fall back to the built-in
    # general-report presenting skeleton so a presenting aspect ALWAYS exists —
    # then loudly recommend deriving a richer one via /artifact-flow. The tool
    # never refuses (NFR3); the default is a conscious-choice nudge, not silence.
    used_default_presenting = workflow_yaml is None
    if used_default_presenting:
        workflow_yaml = DEFAULT_PRESENTING_GRAPH_YAML

    # Parse YAML
    result = parse_workflow_yaml(workflow_yaml)
    if isinstance(result, dict) and "ok" in result and not result["ok"]:
        return result

    graph: dict[str, StateDefinition] = result  # type: ignore[assignment]

    # Permissive (NFR3/KD10): capabilities are a DESCRIPTIVE record, not a gate.
    # When the caller omits them, infer from the graph's own handler types so init
    # never refuses on capability grounds; an explicit list still augments. This
    # also keeps the default-presenting session's caps from locking out powering
    # aspects a later register_workflow declares.
    inferred_caps = sorted({sd.handler_type for sd in graph.values() if sd.handler_type})
    capabilities = sorted(set((capabilities or []) + inferred_caps)) or ["self"]

    # Validate graph (structural: dangling transitions, cycle-with-exit). The
    # capability check now passes by construction since caps include the graph's
    # handlers — it stays as a guard for any future stricter caller.
    error = validate_graph(graph, capabilities)
    if error is not None:
        return error

    # Initialize state
    resp = state_mod.init_state(
        capabilities, graph,
        title=title, description=description, assignee=assignee,
        meta_key=meta_key,
    )

    # Surface the presenting-aspect provenance + the mandatory-declaration nudge.
    if isinstance(resp, dict) and resp.get("ok"):
        if used_default_presenting:
            resp["presenting_aspect"] = "default-general-report"
            resp["recommendation"] = (
                "Using the built-in general-report presenting aspect "
                "(build -> user-review gate -> done). MANDATORY: consciously decide "
                "HOW the user reviews this work — this default is a fallback, not a "
                "choice. For a presenting structure matched to your task class (which "
                "gates the user reviews, which persist with ACs even unreviewed), read "
                "and apply the /artifact-flow skill (ships with the verify-suite "
                "plugin — recommended because the presenting aspect is a core "
                "concept, not required), or pass your own workflow_yaml. "
                "Record gates with ACs so review points stay visible and resumable."
            )
        else:
            resp["presenting_aspect"] = "custom"
    return resp


@mcp.tool()
def advance(target: str, summary: str = "", meta_key: str = "artifact-flow") -> dict:
    """DEFAULT mover — advance to a target state on a LEGAL transition.

    Use this for normal forward progress. Pick a fallback instead when:
    - position is BLOCKED → reset_to (it clears blocked; advance refuses here).
    - you need to REWORK to an earlier state → reset_to.
    - target is OFF-GRAPH (not a legal edge) → override_transition.
    - target is a gate and review was skipped → advance_without_evidence (below).
    - you want to RESHAPE the graph itself → update_workflow (not a move).

    Required:
    - summary: Summary of what was accomplished and current context (<500 words). Write as if a stateless replacement agent will read ONLY this summary to understand where things stand and what to do next. Include: what was done, what's pending, and reference file paths for artifacts rather than dumping content inline. Goal: another lead can resume from this summary alone without re-reading full history.

    Optional:
    - meta_key: which registry member to advance (default "artifact-flow").

    SOFT GATE: if target is a gate: true state with no recorded review evidence,
    this returns a typed SUCCESS with advanced=false (a recommendation, NOT a
    refusal — check the advanced flag, don't assume ok=true means you moved).
    To proceed: either record_review_evidence then retry advance, or call
    advance_without_evidence(target, reason) to record the skip-with-reason.
    """
    return state_mod.advance(target, summary=summary, meta_key=meta_key)


@mcp.tool()
def view_current_state(meta_key: str = "artifact-flow") -> dict:
    """Narrow read: the current state NAME only, for one member.

    Supplement to get_active_plan — prefer get_active_plan for the full picture
    (it already carries current_state plus gates/joins/ACs). Use this only when
    you need the bare scalar and nothing else.
    """
    return state_mod.get_current_state(meta_key=meta_key)


@mcp.tool()
def view_legal_transitions(meta_key: str = "artifact-flow") -> dict:
    """Narrow read: legal transitions from the current state of one member.

    Supplement to get_active_plan — use when you specifically need the set of
    next-legal targets (e.g. before an advance). For the full picture call
    get_active_plan first.
    """
    return state_mod.get_legal_transitions(meta_key=meta_key)


@mcp.tool()
def record_output(
    state: str, output_ref: str, meta_key: str = "artifact-flow"
) -> dict:
    """Record an output reference for a visited state.

    The state must exist in the workflow and must have been visited
    (either as the starting state or via advance). Multiple outputs
    can be recorded per state. Operates on meta_key (default "artifact-flow").
    """
    return state_mod.record_output(state, output_ref, meta_key=meta_key)


@mcp.tool()
def view_history(meta_key: str | None = None) -> dict:
    """Return the append-only history of operations.

    Returns entries in monotonic sequence order with timestamps. History is
    never truncated or modified. History is file-global (tagged per entry with
    meta_key); pass meta_key to filter to one member, omit for the full log.
    """
    return state_mod.view_history(meta_key=meta_key)


@mcp.tool()
def mark_blocked(
    blocker: str = "",
    unblock_condition: str = "",
    impact: str = "",
    meta_key: str = "artifact-flow",
) -> dict:
    """Mark the current workflow position as blocked.

    Prevents advance until recovered via reset_to or override_transition.
    All three fields are required:
    - blocker: What is preventing progress
    - unblock_condition: What needs to happen for this to unblock
    - impact: What is affected or delayed while blocked
    Operates on meta_key (default "artifact-flow").
    """
    return state_mod.mark_blocked(
        blocker, unblock_condition, impact, meta_key=meta_key
    )


@mcp.tool()
def reset_to(
    state: str,
    trigger: str = "",
    context: str = "",
    meta_key: str = "artifact-flow",
) -> dict:
    """REWORK / RECOVER mover — move to any existing state, clearing blocked.

    Use this (not advance) to: rework back to an earlier state, or recover a
    BLOCKED position (advance refuses while blocked; reset_to clears it). Stays
    on-graph in spirit but bypasses the legal-edge check. For a truly off-graph
    force-move, use override_transition. Backward moves reset per-pass join
    accumulators so the next pass starts clean.
    All fields are required:
    - state: Target state to reset to
    - trigger: What changed or was resolved that caused this reset
    - context: Key information or situation that led to this decision
    Operates on meta_key (default "artifact-flow").
    """
    return state_mod.reset_to(state, trigger, context, meta_key=meta_key)


@mcp.tool()
def override_transition(
    target: str,
    reason: str,
    skipped_alternatives: list[str],
    risks: str,
    meta_key: str = "artifact-flow",
) -> dict:
    """Force-move to a target state, bypassing transition rules.

    All parameters are required for auditability. Clears blocked status.
    Documents the override decision in history (reason, skipped alternatives, risks).
    Operates on meta_key (default "artifact-flow"). For advancing into a gate
    without review evidence on a LEGAL edge, use advance_without_evidence instead.
    """
    return state_mod.override_transition(
        target, reason, skipped_alternatives, risks, meta_key=meta_key
    )


@mcp.tool()
def update_workflow(
    workflow_yaml: str,
    reason: str,
    reset_to_state: str | None = None,
    meta_key: str = "artifact-flow",
) -> dict:
    """MODIFY an existing member's graph, archiving the old version.

    For ADDING a new member, use register_workflow instead (this requires the
    meta_key to already exist). Parses and validates the new YAML. If the current state is preserved,
    updates in place. If removed with reset_to_state, atomically resets
    position and updates. If removed without reset_to_state, rejects with
    CURRENT_STATE_REMOVED listing surviving states.
    Operates on meta_key (default "artifact-flow").
    """
    return state_mod.update_workflow(
        workflow_yaml, reason, reset_to_state, meta_key=meta_key
    )


@mcp.tool()
def view_workflow(
    meta_key: str = "artifact-flow", version: int | None = None
) -> dict:
    """Static graph DEFINITION (states, transitions, Mermaid) — NOT live state.

    This shows how the workflow is shaped; it carries NO position, gate, or AC
    status. For where things actually stand, call get_active_plan instead.

    Optional:
    - version: omit for the CURRENT graph; pass an integer to retrieve an
      ARCHIVED snapshot as it existed at that version (formerly view_version).
    - meta_key: which registry member (default "artifact-flow").
    """
    if version is not None:
        return state_mod.view_version(version, meta_key=meta_key)
    return state_mod.view_workflow(meta_key=meta_key)


@mcp.tool()
def update_meta(
    title: str | None = None,
    description: str | None = None,
    exec_summary: str | None = None,
) -> dict:
    """Update SESSION-level fields: title, description, exec_summary.

    Ticket-style metadata for the session as a whole. Does NOT touch the
    workflow graph (use update_workflow) or registry keys. Updates whichever
    fields are provided, leaves others unchanged.
    """
    return state_mod.update_meta(
        title=title, description=description, exec_summary=exec_summary,
    )


@mcp.tool()
def list_sessions() -> dict:
    """List all workflow sessions found under the .task-tool/ directory.

    Scans for workflow-state.json files and returns a summary of each session
    including title, assignee, status, exec_summary, current_state, and file path.

    Does NOT require an active session — can be called before init.
    """
    return state_mod.list_sessions()


@mcp.tool()
def get_active_plan() -> dict:
    """DEFAULT read — the ENTIRE active workgraph in one call. Start here.

    Returns the whole registry (ALL members) for the attached session: each
    member's current_state, ready_gates, waiting_joins, open_acs, and
    graduation_prompts, plus the session status rollup. This is the "where do
    things stand right now" call — invoke it FIRST each turn. (The view_*
    tools are narrow slices of what this already returns; reach for one only
    when you need a single piece. For the static graph shape, use view_workflow.)

    Session-scoped pure READ (MR1, KD8): no .task-tool/ scan, no recency
    resolution, no session latching. The dynamic Workflow READS this to know
    where things stand (KD9); the lead WRITES via advance / record_*.

    No-session contract (NFR1): when nothing is attached, returns a typed success
    {ok: true, active_plan: null, attached: false} with guidance pointing to init
    (new) or list_sessions + resume (existing) — NOT an error.
    """
    return state_mod.get_active_plan()


@mcp.tool()
def register_workflow(meta_key: str, workflow_yaml: str) -> dict:
    """CREATE a new meta-keyed workflow member — typically a POWERING aspect (MR1).

    The session already has its PRESENTING aspect (the member created at init —
    by default keyed "artifact-flow"). Use this to add a POWERING aspect — an explore/build/verify
    lane describing HOW work gets done — alongside it, keyed by a distinct
    meta_key (e.g. "impl-flow", "research-flow"). Members stay isolated state
    machines; the presenting aspect can HOLD on a powering aspect's state by your
    judgment, but no transition table references another member (MR4).

    For MODIFYING an existing member's graph, use update_workflow instead (this
    fails with META_KEY_EXISTS if meta_key is already registered — it never
    clobbers an in-flight member). The member's graph is validated in isolation
    — never against the merged registry — so cross-member transition references
    cannot validate. Requires an active session (init or resume first).
    """
    return state_mod.register_workflow(meta_key, workflow_yaml)


@mcp.tool()
def record_branch_arrival(
    state: str, label: str, meta_key: str = "artifact-flow"
) -> dict:
    """Record that a fan-out branch reported back to a convergence state (MR4).

    Adds label to the convergence state's received set as a SET — idempotent, so
    a retried/duplicated branch report cannot inflate it. Records ARRIVAL
    (presence), NOT outcome: a failed branch still arrives; the converge→rework
    decision is the lead's judgment from the branch's actual result, not stored
    here. label must be declared in the state's join_required.
    """
    return state_mod.record_branch_arrival(state, label, meta_key=meta_key)


@mcp.tool()
def view_join_status(meta_key: str = "artifact-flow") -> dict:
    """Return per-convergence-state "blocked, waiting on X" join status (MR4).

    Computes required − received for every state that declares a join and names
    the missing branches. A focused per-state supplement to get_active_plan's
    waiting_joins field, not a required second call. Member default "artifact-flow".
    """
    return state_mod.view_join_status(meta_key=meta_key)


@mcp.tool()
def record_review_evidence(
    meta_key: str = "artifact-flow", gate_state: str = ""
) -> dict:
    """Record has-review-subagent-checked evidence for a gate state (MR5).

    Use this AFTER a review subagent has checked a gate, BEFORE you advance into
    it — the two-step default path (this, then advance). Not for deliverables
    (record_output) or fan-out branches (record_branch_arrival). Sets the
    evidence flag keyed by the GATE state's name so a subsequent advance into
    that state proceeds without a soft recommendation. Uniform bar for every
    gate — no risk tiers. gate_state must exist in the workflow.
    """
    return state_mod.record_review_evidence(meta_key=meta_key, gate_state=gate_state)


@mcp.tool()
def accumulate_ac(meta_key: str, state: str, ac: dict) -> dict:
    """Accumulate a failed acceptance criterion for a state, deduped + bounded (MR6).

    The `state` arg is ANY existing state name — it need NOT be a gate: true
    state (the gate marker just labels a review checkpoint; ACs are not confined
    to gates, KD10). On AC failure, dedups on AC identity: a re-failing AC bumps
    its hit_count instead of appending a duplicate, so the list stays bounded
    across rework loops. An AC with no stable identity is appended without dedup
    (deduped=false + a soft note) rather than refused. Prior ACs are preserved and
    re-surfaced on the next pass. When hit_count crosses the graduation threshold,
    graduate=true flags the AC for promotion to a durable /verify rule via
    /flag-imp. The ac dict references a verify rule name / short AC key (e.g.
    {"id": "diagram-present", "ac": "..."}), NOT a copied rule body. Tag
    origin: "user" | "ai" for auditable provenance (defaults to "ai" when omitted);
    origin round-trips into get_active_plan's open_acs.
    """
    return state_mod.accumulate_ac(meta_key, state, ac)


@mcp.tool()
def advance_without_evidence(
    target: str, reason: str, meta_key: str = "artifact-flow"
) -> dict:
    """Advance on a LEGAL edge without review evidence, recording the reason (MR5, MR7).

    The recorded soft-gate audit path — use after advance returns advanced=false
    on a gate, when you choose to skip the review subagent. NOT a reuse of
    override_transition: it REQUIRES a LEGAL transition (rejects an off-graph
    target — use override_transition for that) and works on any such target, not
    only gate: true states (KD10). Records ONLY the single reason in history, so
    the audit log distinguishes "advanced without review evidence" (routine,
    reason logged) from "force-moved off-graph" (override_transition, high
    concern). reason is required and non-empty.
    """
    return state_mod.advance_without_evidence(target, reason, meta_key=meta_key)


def main() -> None:
    """Entry point for the task-tool MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
