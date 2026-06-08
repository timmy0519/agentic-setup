"""AC accumulation tests (Phase 11/12): per-gate AC store with dedup + graduation.

Covers US5, MR5, C7 (accumulate + preserve + re-surface, ACs reference /verify
rule names) and KD7 (dedup bumps hit_count, list bounded, threshold crossing
surfaces a graduation prompt via get_active_plan).
"""

from __future__ import annotations

import pytest

from task_tool.yaml_parser import parse_workflow_yaml
from task_tool.validator import validate_graph
from task_tool.state import (
    init_state,
    accumulate_ac,
    get_active_plan,
    AC_GRADUATION_THRESHOLD,
    DEFAULT_META_KEY,
)


# A workflow with a gate state (`review`) that loops back to `draft` for rework,
# so the same gate is re-entered across passes and ACs accumulate.
GATE_WORKFLOW_YAML = """\
states:
  draft:
    handler_type: self
    transitions:
      - review
    input: "Task brief"
    output: "Draft artifact"
  review:
    handler_type: self
    gate: true
    transitions:
      - done
      - draft
    input: "Draft artifact"
    output: "Reviewed artifact"
  done:
    handler_type: self
    transitions: []
    input: "Reviewed artifact"
    output: "Final"
"""


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _init():
    caps = ["self"]
    graph = parse_workflow_yaml(GATE_WORKFLOW_YAML)
    assert not (isinstance(graph, dict) and "ok" in graph and not graph["ok"]), graph
    err = validate_graph(graph, caps)
    assert err is None, err
    result = init_state(caps, graph)
    assert result["ok"] is True, result
    return result


def _member_plan(meta_key: str = DEFAULT_META_KEY) -> dict:
    plan = get_active_plan()
    assert plan["ok"] is True, plan
    assert plan["attached"] is True, plan
    return plan["active_plan"]["members"][meta_key]


# ---------------------------------------------------------------------------
# US5 / MR5 / C7 — accumulate, preserve, re-surface, reference rule names
# ---------------------------------------------------------------------------

class TestAccumulatePreserveResurface:
    def test_gate_failure_appends_new_ac(self):
        _init()
        result = accumulate_ac(DEFAULT_META_KEY, "review", {"id": "diagram-present"})
        assert result["ok"] is True
        assert result["data"]["gate"] == "review"
        assert result["data"]["deduped"] is False
        assert result["data"]["hit_count"] == 1
        assert result["data"]["total_acs"] == 1

    def test_new_failure_preserves_prior_acs(self):
        _init()
        accumulate_ac(DEFAULT_META_KEY, "review", {"id": "diagram-present"})
        result = accumulate_ac(DEFAULT_META_KEY, "review", {"id": "footnote-citations"})
        assert result["ok"] is True
        # Second distinct AC appends without dropping the first.
        assert result["data"]["deduped"] is False
        assert result["data"]["total_acs"] == 2

        # Both ACs are present in the accumulated set for the gate.
        plan = _member_plan()
        open_ac_refs = {a["ac"] for a in plan["open_acs"] if a["state"] == "review"}
        assert open_ac_refs == {"diagram-present", "footnote-citations"}

    def test_accumulated_set_resurfaced_on_next_pass(self):
        # Accumulate two distinct ACs on the gate; the active plan re-surfaces
        # the whole accumulated set (the "next pass" view the lead reads).
        _init()
        accumulate_ac(DEFAULT_META_KEY, "review", {"id": "diagram-present"})
        accumulate_ac(DEFAULT_META_KEY, "review", {"id": "footnote-citations"})

        plan = _member_plan()
        review_acs = [a for a in plan["open_acs"] if a["state"] == "review"]
        assert len(review_acs) == 2
        refs = {a["ac"] for a in review_acs}
        assert refs == {"diagram-present", "footnote-citations"}

    def test_ac_entries_reference_verify_rule_names(self):
        # C7: entries reference rule names / short keys, not copied rule bodies.
        _init()
        accumulate_ac(
            DEFAULT_META_KEY,
            "review",
            {"id": "diagram-present", "ac": "every flow has a mermaid diagram"},
        )
        plan = _member_plan()
        review_acs = [a for a in plan["open_acs"] if a["state"] == "review"]
        assert len(review_acs) == 1
        # The surfaced reference is the rule name / short key, not the body text.
        assert review_acs[0]["ac"] == "diagram-present"

    def test_falls_back_to_ac_text_when_no_rule_name(self):
        # When no id/rule/key is given, identity falls back to the `ac` text so
        # dedup still functions on the only available handle.
        _init()
        accumulate_ac(DEFAULT_META_KEY, "review", {"ac": "missing tldr"})
        result = accumulate_ac(DEFAULT_META_KEY, "review", {"ac": "missing tldr"})
        assert result["data"]["deduped"] is True
        assert result["data"]["hit_count"] == 2
        assert result["data"]["total_acs"] == 1


# ---------------------------------------------------------------------------
# KD7 / MR5 — dedup bumps hit_count, list bounded, threshold graduation
# ---------------------------------------------------------------------------

class TestDedupAndGraduation:
    def test_refailing_same_ac_bumps_hit_count_no_duplicate(self):
        _init()
        r1 = accumulate_ac(DEFAULT_META_KEY, "review", {"id": "diagram-present"})
        assert r1["data"]["hit_count"] == 1
        assert r1["data"]["deduped"] is False

        r2 = accumulate_ac(DEFAULT_META_KEY, "review", {"id": "diagram-present"})
        assert r2["data"]["deduped"] is True
        assert r2["data"]["hit_count"] == 2
        # No duplicate appended — the list stays bounded.
        assert r2["data"]["total_acs"] == 1

    def test_list_bounded_across_many_refails(self):
        _init()
        last = None
        for _ in range(5):
            last = accumulate_ac(DEFAULT_META_KEY, "review", {"id": "diagram-present"})
        assert last["data"]["total_acs"] == 1
        assert last["data"]["hit_count"] == 5

        plan = _member_plan()
        review_acs = [a for a in plan["open_acs"] if a["state"] == "review"]
        assert len(review_acs) == 1
        assert review_acs[0]["hit_count"] == 5

    def test_below_threshold_no_graduation(self):
        _init()
        # One failure (threshold is 3) — not yet graduating.
        result = accumulate_ac(DEFAULT_META_KEY, "review", {"id": "diagram-present"})
        assert result["data"]["graduate"] is False

        plan = _member_plan()
        assert plan["graduation_prompts"] == []

    def test_crossing_threshold_surfaces_graduation_prompt(self):
        _init()
        result = None
        for _ in range(AC_GRADUATION_THRESHOLD):
            result = accumulate_ac(
                DEFAULT_META_KEY, "review", {"id": "diagram-present"}
            )
        # The accumulate call itself signals graduation at the threshold.
        assert result["data"]["hit_count"] == AC_GRADUATION_THRESHOLD
        assert result["data"]["graduate"] is True

        # get_active_plan surfaces a graduation prompt for THAT gate.
        plan = _member_plan()
        prompts = plan["graduation_prompts"]
        assert len(prompts) == 1
        prompt = prompts[0]
        assert prompt["state"] == "review"
        assert prompt["ac"] == "diagram-present"
        assert prompt["hit_count"] == AC_GRADUATION_THRESHOLD
        # The prompt text routes the lead to graduate via /flag-imp.
        assert "graduat" in prompt["prompt"].lower()

    def test_graduation_prompt_only_for_crossing_ac(self):
        # One AC crosses the threshold, another stays below — only the crossing
        # one surfaces a graduation prompt.
        _init()
        for _ in range(AC_GRADUATION_THRESHOLD):
            accumulate_ac(DEFAULT_META_KEY, "review", {"id": "diagram-present"})
        accumulate_ac(DEFAULT_META_KEY, "review", {"id": "footnote-citations"})

        plan = _member_plan()
        prompts = plan["graduation_prompts"]
        assert len(prompts) == 1
        assert prompts[0]["ac"] == "diagram-present"

    def test_accumulate_ac_unknown_gate_errors(self):
        _init()
        result = accumulate_ac(DEFAULT_META_KEY, "nonexistent", {"id": "x"})
        assert result["ok"] is False
        assert result["error"]["code"] == "STATE_NOT_FOUND"

    def test_accumulate_ac_no_session_errors(self):
        # No init — must surface NO_WORKFLOW, not crash.
        result = accumulate_ac(DEFAULT_META_KEY, "review", {"id": "x"})
        assert result["ok"] is False
        assert result["error"]["code"] == "NO_WORKFLOW"


# ---------------------------------------------------------------------------
# PERMISSIVE — ACs attach to ANY existing state, regardless of gate marker
# ---------------------------------------------------------------------------

class TestAccumulateGateGuard:
    def test_accumulate_ac_on_non_gate_state_succeeds_and_surfaces(self):
        """task-tool RECORDS, it does not ENFORCE. `gate: true` is a convention
        marker, not a precondition — an AC accumulates on ANY existing state and
        surfaces in get_active_plan regardless of the gate marker.
        """
        _init()
        # 'draft' exists and is a plain (non-gate) state in GATE_WORKFLOW_YAML.
        result = accumulate_ac(DEFAULT_META_KEY, "draft", {"id": "diagram-present"})
        assert result["ok"] is True, result
        assert result["data"]["gate"] == "draft"
        assert result["data"]["deduped"] is False
        assert result["data"]["total_acs"] == 1

        # The AC surfaces in open_acs, tagged gate=False (not a review checkpoint).
        plan = _member_plan()
        draft_acs = [a for a in plan["open_acs"] if a["state"] == "draft"]
        assert len(draft_acs) == 1
        assert draft_acs[0]["ac"] == "diagram-present"
        assert draft_acs[0]["gate"] is False

    def test_accumulate_ac_on_gate_state_marks_gate_true(self):
        """An AC on a gate:true state surfaces with gate=True (review checkpoint)."""
        _init()
        result = accumulate_ac(DEFAULT_META_KEY, "review", {"id": "diagram-present"})
        assert result["ok"] is True
        plan = _member_plan()
        review_acs = [a for a in plan["open_acs"] if a["state"] == "review"]
        assert len(review_acs) == 1
        assert review_acs[0]["gate"] is True


# ---------------------------------------------------------------------------
# PERMISSIVE — anonymous ACs append (no dedup), they are NOT refused
# ---------------------------------------------------------------------------

class TestAnonymousACRejected:
    def test_anonymous_ac_appends_with_deduped_false(self):
        """An AC with no id/rule/key/ac (empty identity) APPENDS unconditionally
        with deduped=false + a soft note — it is NOT refused. Recording state is
        the job; dedup is a convenience that only applies to identity-bearing ACs.
        """
        _init()
        result = accumulate_ac(DEFAULT_META_KEY, "review", {})
        assert result["ok"] is True, result
        assert result["data"]["deduped"] is False
        assert result["data"]["total_acs"] == 1
        assert "note" in result["data"]

    def test_two_anonymous_acs_both_append(self):
        """Two anonymous-AC calls each append (no dedup key to collapse them)."""
        _init()
        accumulate_ac(DEFAULT_META_KEY, "review", {})
        accumulate_ac(DEFAULT_META_KEY, "review", {})
        plan = _member_plan()
        review_acs = [a for a in plan["open_acs"] if a["state"] == "review"]
        assert len(review_acs) == 2

    def test_whitespace_only_identity_appends_without_dedup(self):
        """An AC whose identity fields are whitespace-only has no stable identity,
        so it appends without dedup (deduped=false + note), not refused."""
        _init()
        result = accumulate_ac(DEFAULT_META_KEY, "review", {"id": "   "})
        assert result["ok"] is True
        assert result["data"]["deduped"] is False
        assert "note" in result["data"]


# ---------------------------------------------------------------------------
# ADD — AC provenance (origin) round-trips and surfaces in open_acs
# ---------------------------------------------------------------------------

class TestACOrigin:
    def test_user_origin_round_trips(self):
        """origin='user' is stored faithfully and surfaces in open_acs."""
        _init()
        result = accumulate_ac(
            DEFAULT_META_KEY, "review", {"id": "user-req", "origin": "user"}
        )
        assert result["ok"] is True
        assert result["data"]["origin"] == "user"
        plan = _member_plan()
        ac = next(a for a in plan["open_acs"] if a["ac"] == "user-req")
        assert ac["origin"] == "user"

    def test_ai_origin_round_trips(self):
        """origin='ai' is stored faithfully and surfaces in open_acs."""
        _init()
        result = accumulate_ac(
            DEFAULT_META_KEY, "review", {"id": "ai-add", "origin": "ai"}
        )
        assert result["ok"] is True
        assert result["data"]["origin"] == "ai"
        plan = _member_plan()
        ac = next(a for a in plan["open_acs"] if a["ac"] == "ai-add")
        assert ac["origin"] == "ai"

    def test_origin_defaults_to_ai_when_omitted(self):
        """An unattributed AC is treated as the lead-AI's own addition: origin='ai'."""
        _init()
        result = accumulate_ac(DEFAULT_META_KEY, "review", {"id": "no-origin"})
        assert result["ok"] is True
        assert result["data"]["origin"] == "ai"
        plan = _member_plan()
        ac = next(a for a in plan["open_acs"] if a["ac"] == "no-origin")
        assert ac["origin"] == "ai"

    def test_invalid_origin_falls_back_to_ai(self):
        """A non-truthful origin value (not user/ai) defaults to 'ai'."""
        _init()
        result = accumulate_ac(
            DEFAULT_META_KEY, "review", {"id": "bad-origin", "origin": "robot"}
        )
        assert result["ok"] is True
        assert result["data"]["origin"] == "ai"
