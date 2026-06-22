import json
from argparse import Namespace

from runners.run_webshop_shadow import run
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
            "post_check": {"info_gain": False},
        }
    )
    assert run_pre_check(record, state)["repeat_known_no_info"] is True


def test_post_only_detects_new_attribute_values():
    before = extract_observation_attributes("Search page", {"clickables": ["search"]}, step=0)
    after = extract_observation_attributes(
        "Search results [SEP] B08K7LDM7Q [SEP] Good Pillow [SEP] $29.99",
        {"clickables": ["B08K7LDM7Q"]},
        step=1,
    )
    post = run_post_check(before, after, after["context.current"]["current_value"])
    assert post["info_gain"] is True
    assert any(item["key"] == "entity.b08k7ldm7q" for item in post["new_attrs"])


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
    rows = [
        json.loads(line)
        for line in (tmp_path / "logs" / "trajectories.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 2
    for trajectory in rows:
        assert set(trajectory["shadow_state"]) == {"attributes", "actions"}
        for step in trajectory["steps"]:
            record = step["action_record"]
            assert record["executed_action"] == record["raw"]
            assert set(record["pre_check"]) == {"format_valid", "repeat_known_no_info"}
            assert set(record["post_check"]) == {"info_gain", "new_attrs", "context_after"}
