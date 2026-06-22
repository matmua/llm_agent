import json
from argparse import Namespace

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


def test_post_marks_fifth_consecutive_signature_as_trajectory_risk_even_with_delta():
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
    for _ in range(4):
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
    assert post["same_action_signature_streak"] == 5
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
            log_dir=str(tmp_path / "logs"),
            report_dir=str(tmp_path / "reports"),
        )
    )
    metrics = result["metrics"]
    assert metrics["state_to_agent"] is False
    assert metrics["repair_enabled"] is False
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
