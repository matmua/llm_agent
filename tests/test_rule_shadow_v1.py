import json
from argparse import Namespace

from agents.react_agent import WebShopReactAgent
from runners.run_webshop_shadow import build_trajectory_risk_summary, run
from shadow.extractor import extract_observation_attributes
from shadow.parser import action_signature, parse_action
from shadow.post import run_post_check
from shadow.pre import run_pre_check
from shadow.repair import propose_repair
from shadow.state import check_params, merge_attributes, new_shadow_state


def test_parser_is_format_only():
    parsed = parse_action("click[B08K7LDM7Q]")
    assert parsed["format_valid"] is True
    assert parsed["type"] == "click"
    assert parsed["params"] == {"target": "B08K7LDM7Q"}
    assert parse_action("click[]")["format_valid"] is False


def test_extractor_uses_two_table_attribute_schema():
    attrs = extract_observation_attributes(
        "Instruction [SEP] B08K7LDM7Q [SEP] Good Pillow [SEP] $29.99 [SEP] buy now",
        {"clickables": ["B08K7LDM7Q", "buy now"], "has_search_bar": False},
        step=0,
    )
    assert "context.current" in attrs
    assert "entity.b08k7ldm7q" in attrs
    assert "attr.b08k7ldm7q.price" in attrs
    assert attrs["entity.b08k7ldm7q"]["kind"] == "entity"


def test_param_known_check_records_without_error_rule():
    state = new_shadow_state()
    attrs = extract_observation_attributes(
        "B08K7LDM7Q [SEP] Good Pillow [SEP] $29.99",
        {"clickables": ["B08K7LDM7Q"], "has_search_bar": False},
        step=0,
    )
    merge_attributes(state, attrs)
    parsed = parse_action("click[B08K7LDM7Q]")
    checks = check_params(parsed, state["attributes"])
    assert checks["target"]["known"] is True
    assert checks["target"]["matched_attr"] == "entity.b08k7ldm7q"


def test_pre_only_detects_format_and_repeated_no_info():
    state = new_shadow_state()
    parsed = parse_action("click[next >]")
    record = {
        "parsed_action": parsed,
        "context_before": "ctx_a",
        "action_signature": action_signature(parsed),
    }
    assert run_pre_check(record, state) == {
        "format_valid": True,
        "repeat_known_no_info": False,
    }
    state["actions"].append(
        {
            "context_before": "ctx_a",
            "action_signature": action_signature(parsed),
            "post_check": {"visible_delta": False, "info_gain": False},
        }
    )
    assert run_pre_check(record, state)["repeat_known_no_info"] is False
    state["actions"].append(
        {
            "context_before": "ctx_a",
            "action_signature": action_signature(parsed),
            "post_check": {"visible_delta": False, "info_gain": False},
        }
    )
    assert run_pre_check(record, state)["repeat_known_no_info"] is True


def test_post_separates_visible_delta_from_no_progress():
    state = new_shadow_state()
    before = extract_observation_attributes("Search page", {"clickables": ["search"]}, step=0)
    merge_attributes(state, before)
    after = extract_observation_attributes(
        "Search results [SEP] B08K7LDM7Q [SEP] Good Pillow [SEP] $29.99",
        {"clickables": ["B08K7LDM7Q"]},
        step=1,
    )
    parsed = parse_action("search[pillow]")
    record = {
        "context_before": "ctx_a",
        "action_signature": action_signature(parsed),
    }
    post = run_post_check(before, after, record, state, after["context.current"]["current_value"])
    assert post["info_gain"] is True
    assert post["visible_delta"] is True
    assert post["no_progress"] is False
    assert post["same_action_no_visible_delta_count"] == 0
    assert post["same_action_signature_streak"] == 1
    assert post["repeated_behavior_risk"] is False
    assert post["repeated_behavior_reason"] is None
    assert any(item["key"] == "entity.b08k7ldm7q" for item in post["new_attrs"])

    no_delta = run_post_check(before, before, record, state, before["context.current"]["current_value"])
    assert no_delta["visible_delta"] is False
    assert no_delta["no_progress"] is False
    assert no_delta["same_action_no_visible_delta_count"] == 1
    assert no_delta["same_action_signature_streak"] == 1


def test_post_marks_third_same_action_without_visible_delta_as_no_progress():
    state = new_shadow_state()
    attrs = extract_observation_attributes("Same page", {"clickables": ["next >"]}, step=0)
    parsed = parse_action("click[next >]")
    record = {
        "context_before": "ctx_a",
        "action_signature": action_signature(parsed),
    }
    for _ in range(2):
        state["actions"].append(
            {
                "context_before": "ctx_a",
                "action_signature": action_signature(parsed),
                "post_check": {"visible_delta": False, "info_gain": False, "context_after": "ctx_a"},
            }
        )
    post = run_post_check(attrs, attrs, record, state, attrs["context.current"]["current_value"])
    assert post["visible_delta"] is False
    assert post["same_action_no_visible_delta_count"] == 3
    assert post["no_progress"] is True
    assert post["no_progress_reason"] == "same_action_repeated_without_visible_delta"


def test_post_marks_third_consecutive_signature_as_trajectory_risk_even_with_delta():
    state = new_shadow_state()
    before = extract_observation_attributes("Search page", {"clickables": ["next >"]}, step=0)
    after = extract_observation_attributes(
        "Search results [SEP] B08K7LDM7Q [SEP] Good Pillow [SEP] $29.99",
        {"clickables": ["next >", "B08K7LDM7Q"]},
        step=1,
    )
    parsed = parse_action("click[next >]")
    signature = action_signature(parsed)
    record = {
        "context_before": "ctx_a",
        "action_signature": signature,
    }
    for _ in range(2):
        state["actions"].append(
            {
                "context_before": "ctx_a",
                "action_signature": signature,
                "post_check": {"visible_delta": True, "info_gain": True, "context_after": "ctx_b"},
            }
        )
    post = run_post_check(before, after, record, state, after["context.current"]["current_value"])
    assert post["visible_delta"] is True
    assert post["no_progress"] is False
    assert post["same_action_no_visible_delta_count"] == 0
    assert post["same_action_signature_streak"] == 3
    assert post["repeated_behavior_risk"] is True
    assert post["repeated_behavior_reason"] == "same_action_signature_streak"


def test_post_detects_context_cycle_without_visible_delta():
    state = new_shadow_state()
    attrs = extract_observation_attributes("Same page", {"clickables": ["toggle"]}, step=0)
    parsed = parse_action("click[toggle]")
    record = {
        "context_before": "ctx_a",
        "action_signature": action_signature(parsed),
    }
    for context in ["ctx_a", "ctx_b", "ctx_a"]:
        state["actions"].append(
            {
                "context_before": "other",
                "action_signature": "other",
                "post_check": {"visible_delta": False, "info_gain": False, "context_after": context},
            }
        )
    post = run_post_check(attrs, attrs, record, state, "ctx_b")
    assert post["context_cycle_detected"] is True
    assert post["no_progress"] is True
    assert post["no_progress_reason"] == "context_cycle_without_visible_delta"


def test_trajectory_risk_summary_separates_action_and_trajectory_signals():
    steps = [
        {
            "step": 4,
            "action_record": {
                "step": 4,
                "action_signature": "click|target=next >",
                "post_check": {
                    "no_progress": False,
                    "no_progress_reason": None,
                    "same_action_signature_streak": 5,
                    "repeated_behavior_risk": True,
                    "repeated_behavior_reason": "same_action_signature_streak",
                },
            },
        },
        {
            "step": 6,
            "action_record": {
                "step": 6,
                "action_signature": "click|target=toggle",
                "post_check": {
                    "no_progress": True,
                    "no_progress_reason": "context_cycle_without_visible_delta",
                    "same_action_no_visible_delta_count": 1,
                    "repeated_behavior_risk": False,
                    "repeated_behavior_reason": None,
                },
            },
        },
    ]
    summary = build_trajectory_risk_summary(steps)
    assert summary["has_action_no_progress"] is True
    assert summary["has_repeated_behavior_risk"] is True
    assert summary["has_context_cycle_risk"] is True
    assert summary["has_any_risk"] is True
    assert summary["first_repeated_behavior_risk_step"] == 4
    assert summary["first_no_progress_step"] == 6
    assert summary["first_context_cycle_step"] == 6
    assert summary["first_any_risk_step"] == 4


def test_repair_placeholder_is_noop():
    assert propose_repair({}, {}) == {
        "enabled": False,
        "decision": None,
        "new_action": None,
    }


def test_mock_runner_keeps_state_out_of_agent_and_actions_unchanged(tmp_path):
    result = run(
        Namespace(
            env="mock",
            webshop_repo="external/webshop",
            num_products=1000,
            num_samples=2,
            start_index=0,
            max_steps=5,
            model="mock",
            state_to_agent="false",
            llm_risk_verify="false",
            risk_verify_model="",
            risk_verify_recent_steps=6,
            risk_verify_temperature=0.0,
            repair_hint_enabled="false",
            log_dir=str(tmp_path / "logs"),
            report_dir=str(tmp_path / "reports"),
        )
    )
    metrics = result["metrics"]
    assert metrics["state_to_agent"] is False
    assert metrics["repair_enabled"] is False
    assert metrics["repair_hint_enabled"] is False
    assert metrics["repair_hint_to_agent"] is False
    assert metrics["repeated_behavior_risk_threshold"] == 3
    assert metrics["state_prompt_leak_count"] == 0
    assert metrics["action_changed_count"] == 0
    assert "repeated_behavior_risk_action_count" in metrics
    assert "trajectory_risk_sample_count" in metrics
    rows = [
        json.loads(line)
        for line in (tmp_path / "logs" / "trajectories.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 2
    for trajectory in rows:
        assert "trajectory_risk_summary" in trajectory
        assert set(trajectory["shadow_state"]) == {"attributes", "actions"}
        for step in trajectory["steps"]:
            record = step["action_record"]
            assert record["executed_action"] == record["raw"]
            assert record["raw_action"] == record["raw"]
            assert set(record["risk_verifications"]) == {"pre", "post"}
            for verification in record["risk_verifications"].values():
                assert verification == {
                    "enabled": False,
                    "triggered": False,
                    "called": False,
                    "is_error": False,
                    "error_type": "none",
                    "confidence": 0.0,
                    "repair_hint": "",
                    "avoid_action": None,
                    "raw_response": None,
                    "parse_error": None,
                }
            assert record["repair"]["enabled"] is False
            assert record["repair"]["hint_applied_from_previous_step"]["applied"] is False
            assert record["repair"]["pre_repair_attempted"] is False
            assert record["repair"]["post_hint_created"] is False
            assert set(record["pre_check"]) == {"format_valid", "repeat_known_no_info"}
            assert set(record["post_check"]) == {
                "visible_delta",
                "info_gain",
                "new_attrs",
                "same_action_no_visible_delta_count",
                "context_cycle_detected",
                "same_action_signature_streak",
                "repeated_behavior_risk",
                "repeated_behavior_reason",
                "no_progress",
                "no_progress_reason",
                "context_before",
                "context_after",
                "context_changed",
                "new_context",
            }


def test_mock_runner_uses_task_indices_file(tmp_path):
    task_file = tmp_path / "task_ids.json"
    task_file.write_text(json.dumps([1, 0]), encoding="utf-8")
    result = run(
        Namespace(
            env="mock",
            webshop_repo="external/webshop",
            num_products=1000,
            num_samples=99,
            start_index=0,
            task_indices_file=str(task_file),
            max_steps=3,
            model="mock",
            state_to_agent="false",
            llm_risk_verify="false",
            risk_verify_model="",
            risk_verify_recent_steps=6,
            risk_verify_temperature=0.0,
            repair_hint_enabled="false",
            log_dir=str(tmp_path / "logs_random"),
            report_dir=str(tmp_path / "reports_random"),
        )
    )
    assert result["config"]["task_ids"] == [1, 0]
    assert result["metrics"]["num_samples"] == 2
    rows = [
        json.loads(line)
        for line in (tmp_path / "logs_random" / "trajectories.jsonl").read_text().splitlines()
    ]
    assert [row["task_id"] for row in rows] == [1, 0]

def test_agent_prompt_filters_internal_history_fields():
    prompt = WebShopReactAgent._build_prompt(
        task_instruction="Instruction: find a mug",
        observation="Search page",
        available_actions={"has_search_bar": True, "clickables": ["Mug", "buy now"]},
        state_summary="",
        repair_hint="",
        action_history=[
            {
                "step": 0,
                "raw_action": "search[mug]",
                "executed_action": "search[mug]",
                "action_changed": False,
                "pre_check": {"format_valid": True},
                "post_check": {"info_gain": True},
                "risk_verifications": {"post": {"is_error": True}},
                "repair": {"post_hint_created": True},
                "repair_hint": "hidden",
                "visible_delta": True,
                "no_progress": False,
                "repeated_behavior_risk": False,
                "confidence": 0.99,
                "is_error": True,
                "reward": 0.0,
                "done": False,
            }
        ],
    )
    assert "Recent action history:" in prompt
    assert "raw_action" in prompt
    assert "executed_action" in prompt
    assert "reward" in prompt
    assert "done" in prompt
    forbidden = [
        "action_changed",
        "pre_check",
        "post_check",
        "risk_verifications",
        "repair",
        "repair_hint",
        "visible_delta",
        "no_progress",
        "repeated_behavior_risk",
        "confidence",
        "is_error",
        "hidden",
    ]
    for item in forbidden:
        assert item not in prompt


def test_verify_only_and_baseline_prompts_are_identical_without_repair_hint():
    history = [
        {
            "step": 0,
            "raw_action": "search[mug]",
            "executed_action": "search[mug]",
            "reward": 0.0,
            "done": False,
        }
    ]
    baseline_prompt = WebShopReactAgent._build_prompt(
        task_instruction="Instruction: find a mug",
        observation="Search results",
        available_actions={"has_search_bar": True, "clickables": ["Mug"]},
        state_summary="",
        repair_hint="",
        action_history=history,
    )
    verify_only_prompt = WebShopReactAgent._build_prompt(
        task_instruction="Instruction: find a mug",
        observation="Search results",
        available_actions={"has_search_bar": True, "clickables": ["Mug"]},
        state_summary="",
        repair_hint="",
        action_history=[
            {
                **history[0],
                "action_changed": False,
                "risk_verifications": {"post": {"is_error": True}},
                "repair": {"post_hint_created": False},
            }
        ],
    )
    assert baseline_prompt == verify_only_prompt
    assert "Risk-control hint" not in baseline_prompt
    assert "Current task state summary" not in baseline_prompt


def test_repair_hint_is_plain_text_block_not_history_field():
    prompt = WebShopReactAgent._build_prompt(
        task_instruction="Instruction: find a mug",
        observation="Search results",
        available_actions={"has_search_bar": True, "clickables": ["Mug", "back to search"]},
        state_summary="",
        repair_hint=(
            "Risk-control hint for this action:\n"
            "The previous behavior was verified as repetitive. Avoid repeating click[next >]."
        ),
        action_history=[
            {
                "step": 0,
                "raw_action": "click[next >]",
                "executed_action": "click[next >]",
                "reward": 0.0,
                "done": False,
            }
        ],
    )
    assert "Risk-control hint for this action:" in prompt
    hint_index = prompt.index("Risk-control hint for this action:")
    history_index = prompt.index("Recent action history:")
    assert hint_index < history_index
    assert '"repair_hint"' not in prompt
    assert "'repair_hint'" not in prompt
