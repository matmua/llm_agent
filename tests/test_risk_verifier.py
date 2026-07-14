import json

from intervention.risk_verifier import (
    build_risk_package,
    format_available_actions,
    parse_verifier_response,
    verify_post_risk_if_triggered,
    verify_pre_risk_if_triggered,
    verify_risk_if_triggered,
)


class JsonClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def chat(self, messages, temperature=0.0, max_tokens=512):
        self.calls += 1
        return json.dumps(self.payload)


def _risk_action(step=4):
    return {
        "step": step,
        "raw": "click[next >]",
        "raw_action": "click[next >]",
        "type": "click",
        "params": {"target": "next >"},
        "parsed_action": {
            "type": "click",
            "params": {"target": "next >"},
            "format_valid": True,
        },
        "context_before": "ctx_a",
        "action_signature": "click|target=next >",
        "param_checks": {},
        "pre_check": {"format_valid": True, "repeat_known_no_info": False},
        "post_check": {
            "visible_delta": True,
            "same_action_signature_streak": 5,
            "same_action_no_visible_delta_count": 0,
            "context_cycle_detected": False,
            "no_progress": False,
            "no_progress_reason": None,
            "repeated_behavior_risk": True,
            "repeated_behavior_reason": "same_action_signature_streak",
            "context_before": "ctx_a",
            "context_after": "ctx_b",
        },
    }


def test_parse_verifier_response_accepts_legacy_five_fields():
    raw = json.dumps(
        {
            "is_error": True,
            "error_type": "loop_or_repetition",
            "confidence": 0.82,
            "repair_hint": "Stop repeating this action.",
            "avoid_action": "click[next >]",
        }
    )
    parsed = parse_verifier_response(raw)
    assert parsed["called"] is True
    assert parsed["is_error"] is True
    assert parsed["error_type"] == "loop_or_repetition"
    assert parsed["parse_error"] is None

    invalid = parse_verifier_response('{"is_error": false, "error_type": "none"}')
    assert invalid["is_error"] is False
    assert invalid["parse_error"].startswith("invalid_fields")

def test_parse_verifier_response_accepts_extended_progress_fields():
    raw = json.dumps(
        {
            "is_error": True,
            "error_type": "loop_or_repetition",
            "confidence": 0.82,
            "repair_hint": "Choose a task-relevant action.",
            "avoid_action": "click[details]",
            "is_recoverable": True,
            "progress_assessment": "no_progress",
            "should_intervene": "soft",
            "missing_requirement": "task-relevant evidence",
            "suggested_next_action_type": "inspect a different visible option",
        }
    )
    parsed = parse_verifier_response(raw)
    assert parsed["parse_error"] is None
    assert parsed["is_error"] is True
    assert parsed["is_recoverable"] is True
    assert parsed["progress_assessment"] == "no_progress"
    assert parsed["should_intervene"] == "soft"
    assert parsed["missing_requirement"] == "task-relevant evidence"

    invalid = parse_verifier_response(
        json.dumps(
            {
                "is_error": True,
                "error_type": "loop_or_repetition",
                "confidence": 0.82,
                "repair_hint": "Choose a task-relevant action.",
                "avoid_action": "click[details]",
                "is_recoverable": True,
                "progress_assessment": "stalled",
                "should_intervene": "soft",
                "missing_requirement": "task-relevant evidence",
                "suggested_next_action_type": "inspect a different visible option",
            }
        )
    )
    assert invalid["parse_error"] == "invalid_progress_assessment"


def test_non_error_output_must_be_conservative_shape():
    raw = json.dumps(
        {
            "is_error": False,
            "error_type": "none",
            "confidence": 0.35,
            "repair_hint": "",
            "avoid_action": None,
        }
    )
    parsed = parse_verifier_response(raw)
    assert parsed["is_error"] is False
    assert parsed["error_type"] == "none"
    assert parsed["confidence"] == 0.35
    assert parsed["parse_error"] is None

    invalid = json.dumps(
        {
            "is_error": False,
            "error_type": "loop_or_repetition",
            "confidence": 0.3,
            "repair_hint": "",
            "avoid_action": None,
        }
    )
    assert parse_verifier_response(invalid)["parse_error"] == "invalid_non_error_type"


def test_verify_risk_fallbacks_do_not_call_llm_when_disabled_or_unavailable():
    action = _risk_action()
    client = JsonClient(
        {
            "is_error": True,
            "error_type": "loop_or_repetition",
            "confidence": 0.9,
            "repair_hint": "Change strategy.",
            "avoid_action": "click[next >]",
        }
    )
    disabled = verify_risk_if_triggered(
        action_record=action,
        shadow_state={"actions": []},
        task="task",
        current_observation="obs",
        available_actions={"has_search_bar": True, "clickables": ["next >"]},
        enabled=False,
        client=client,
    )
    assert disabled == {
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
    assert client.calls == 0

    unavailable = verify_risk_if_triggered(
        action_record=action,
        shadow_state={"actions": []},
        task="task",
        current_observation="obs",
        available_actions={"has_search_bar": True, "clickables": ["next >"]},
        enabled=True,
        client=None,
    )
    assert unavailable["triggered"] is True
    assert unavailable["called"] is False
    assert unavailable["parse_error"] == "llm_client_unavailable"


def test_pre_and_post_verifiers_are_stage_specific():
    pre_action = _risk_action()
    pre_action["pre_check"] = {"format_valid": False, "repeat_known_no_info": False}
    pre_action["post_check"] = {}
    client = JsonClient(
        {
            "is_error": True,
            "error_type": "format_error",
            "confidence": 0.8,
            "repair_hint": "Use the required format.",
            "avoid_action": None,
        }
    )
    pre_result = verify_pre_risk_if_triggered(
        action_record=pre_action,
        shadow_state={"actions": []},
        task="task",
        current_observation="before",
        available_actions={"has_search_bar": True, "clickables": ["next >"]},
        enabled=True,
        client=client,
    )
    assert pre_result["is_error"] is True
    assert client.calls == 1

    post_result = verify_post_risk_if_triggered(
        action_record=pre_action,
        shadow_state={"actions": []},
        task="task",
        current_observation="after",
        available_actions={"has_search_bar": True, "clickables": ["next >"]},
        enabled=True,
        client=client,
    )
    assert post_result["triggered"] is False
    assert client.calls == 1


def test_build_risk_package_limits_recent_trace_and_omits_outcome_labels():
    current = _risk_action(step=8)
    previous = []
    for step in range(6):
        record = _risk_action(step=step)
        record["raw_action"] = f"click[item-{step}]"
        record["raw"] = record["raw_action"]
        record["action_signature"] = f"click|target=item-{step}"
        previous.append(record)
    package = build_risk_package(
        action_record=current,
        shadow_state={"actions": previous},
        task="find a product",
        current_observation="current page",
        available_actions={"has_search_bar": True, "clickables": ["next >", "buy now"]},
        max_recent_steps=3,
    )
    assert package["risk_trigger"] == {
        "stage": "post",
        "step": 8,
        "signal": "repeated_behavior_risk",
        "candidate_error_type": "loop_or_repetition",
    }
    assert package["available_actions"] == ["search[...]", "click[next >]", "click[buy now]"]
    assert [item["step"] for item in package["recent_trace"]] == [4, 5, 8]
    assert "success" not in json.dumps(package)
    assert "reward" not in json.dumps(package)


def test_format_available_actions_accepts_generic_command_and_tool_schemas():
    actions = format_available_actions(
        {
            "commands": ["pytest tests/test_app.py"],
            "tools": [{"tool": "final_answer"}],
        }
    )
    assert actions == ["pytest tests/test_app.py", "final_answer"]


def test_format_available_actions_accepts_tool_name_mapping_schema():
    actions = format_available_actions(
        {
            "tools": {
                "read_file": {"description": "Read a file"},
                "final_answer": {},
            }
        }
    )
    assert actions == ["read_file", "final_answer"]


def test_build_risk_package_includes_generic_available_actions():
    current = _risk_action(step=8)
    package = build_risk_package(
        action_record=current,
        shadow_state={"actions": []},
        task="fix a bug",
        current_observation="ready to test",
        available_actions={"commands": ["pytest tests/test_app.py"], "tools": [{"tool": "final_answer"}]},
        max_recent_steps=3,
    )
    assert package["available_actions"] == ["pytest tests/test_app.py", "final_answer"]
