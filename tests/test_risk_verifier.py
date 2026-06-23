import json

from intervention.risk_verifier import (
    build_risk_package,
    parse_verifier_response,
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


def test_parse_verifier_response_requires_exact_five_fields():
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


def test_non_error_output_must_be_conservative_shape():
    raw = json.dumps(
        {
            "is_error": False,
            "error_type": "none",
            "confidence": 0.0,
            "repair_hint": "",
            "avoid_action": None,
        }
    )
    parsed = parse_verifier_response(raw)
    assert parsed["is_error"] is False
    assert parsed["error_type"] == "none"
    assert parsed["parse_error"] is None

    invalid = json.dumps(
        {
            "is_error": False,
            "error_type": "none",
            "confidence": 0.3,
            "repair_hint": "",
            "avoid_action": None,
        }
    )
    assert parse_verifier_response(invalid)["parse_error"] == "invalid_non_error_confidence"


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
        "stage": "trajectory",
        "step": 8,
        "signal": "repeated_behavior_risk",
        "candidate_error_type": "loop_or_repetition",
    }
    assert package["available_actions"] == ["search[...]", "click[next >]", "click[buy now]"]
    assert [item["step"] for item in package["recent_trace"]] == [4, 5, 8]
    assert "success" not in json.dumps(package)
    assert "reward" not in json.dumps(package)

