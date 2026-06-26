from intervention.repair_hint import (
    build_repair_hint,
    format_hint_for_agent,
    mark_hint_outcome,
    should_apply_pre_repair,
    should_create_post_hint,
)


def test_repair_hint_decisions_and_repeated_behavior_template():
    verification = {
        "is_error": True,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change strategy.",
        "avoid_action": "click[next >]",
    }
    record = {
        "step": 5,
        "raw_action": "click[next >]",
        "executed_action": "click[next >]",
        "post_check": {
            "repeated_behavior_risk": True,
            "context_cycle_detected": False,
            "no_progress": False,
        },
    }
    assert should_apply_pre_repair(verification, repair_enabled=True) is True
    assert should_apply_pre_repair(verification, repair_enabled=False) is False
    assert should_create_post_hint(verification, repair_enabled=True) is True

    hint = build_repair_hint(verification, "post", record)
    prompt = format_hint_for_agent(hint)
    assert prompt.startswith("Risk-control hint for this action:\n")
    assert "The previous behavior was verified as repeated exploration." in prompt
    assert "Avoid repeating this action: click[next >]." in prompt
    assert "If a suitable candidate or completion action is available" in prompt
    assert '"repair_hint"' not in prompt
    assert "error_type" not in prompt
    assert "confidence" not in prompt
    assert mark_hint_outcome(hint, "click[next >]")["followed"] is False
    assert mark_hint_outcome(hint, "click[item]")["followed"] is True


def test_loop_hint_without_avoid_action_uses_strong_template_without_avoid_line():
    verification = {
        "is_error": True,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change strategy.",
        "avoid_action": None,
    }
    record = {
        "step": 6,
        "raw_action": "click[item]",
        "executed_action": "click[item]",
        "post_check": {"repeated_behavior_risk": True},
    }
    hint = build_repair_hint(verification, "pre", record)
    prompt = format_hint_for_agent(hint)
    assert prompt.startswith("Risk-control hint for this action:\n")
    assert "Do not continue the same action or strategy." in prompt
    assert "Avoid repeating this action" not in prompt
    assert mark_hint_outcome(hint, "click[item]")["followed"] is False


def test_loop_hint_context_cycle_template():
    verification = {
        "is_error": True,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change strategy.",
        "avoid_action": "click[back]",
    }
    record = {
        "step": 2,
        "raw_action": "click[back]",
        "executed_action": "click[back]",
        "post_check": {
            "repeated_behavior_risk": False,
            "context_cycle_detected": True,
            "no_progress": True,
        },
    }
    prompt = format_hint_for_agent(build_repair_hint(verification, "post", record))
    assert "A context cycle was verified." in prompt
    assert "Do not return to the same repeated context again." in prompt
    assert "Avoid repeating this action" not in prompt


def test_loop_hint_local_no_progress_template():
    verification = {
        "is_error": True,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change strategy.",
        "avoid_action": "click[7]",
    }
    record = {
        "step": 3,
        "raw_action": "click[7]",
        "executed_action": "click[7]",
        "post_check": {
            "repeated_behavior_risk": False,
            "context_cycle_detected": False,
            "no_progress": True,
        },
    }
    prompt = format_hint_for_agent(build_repair_hint(verification, "post", record))
    assert "A local repeated action was verified." in prompt
    assert "If the current observation already provides a valid action" in prompt
    assert "Avoid repeating this action" not in prompt


def test_format_error_template():
    prompt = format_hint_for_agent(
        build_repair_hint(
            {
                "is_error": True,
                "error_type": "format_error",
                "repair_hint": "Use format.",
                "avoid_action": None,
            },
            "pre",
            {"step": 0, "raw_action": "I choose item"},
        )
    )
    assert "The previous action format was invalid." in prompt
    assert "Generate a valid action using exactly one of the required formats." in prompt
    assert "Do not explain." in prompt


def test_evidence_guessing_template():
    prompt = format_hint_for_agent(
        build_repair_hint(
            {
                "is_error": True,
                "error_type": "evidence_guessing",
                "repair_hint": "Do not invent.",
                "avoid_action": None,
            },
            "pre",
            {"step": 0, "raw_action": "click[unknown]"},
        )
    )
    assert "The previous action may rely on unsupported information." in prompt
    assert "recent confirmed evidence" in prompt
    assert "Do not invent unseen parameters." in prompt


def test_wrong_action_or_param_template_with_avoid_action():
    prompt = format_hint_for_agent(
        build_repair_hint(
            {
                "is_error": True,
                "error_type": "wrong_action_or_param",
                "repair_hint": "Wrong item.",
                "avoid_action": "click[bad]",
            },
            "post",
            {"step": 4, "raw_action": "click[bad]", "executed_action": "click[bad]"},
        )
    )
    assert "The previous action or parameter may not match the task requirement" in prompt
    assert "Do not repeat the same unsuitable action." in prompt
    assert "Avoid repeating this action: click[bad]." in prompt


def test_none_error_type_does_not_generate_hint():
    prompt = format_hint_for_agent(
        build_repair_hint(
            {
                "is_error": False,
                "error_type": "none",
                "repair_hint": "",
                "avoid_action": None,
            },
            "post",
            {"step": 0, "raw_action": "search[mug]", "executed_action": "search[mug]"},
        )
    )
    assert prompt == ""
