from intervention.repair_hint import (
    build_repair_hint,
    format_hint_for_agent,
    format_pre_repair_hint_for_agent,
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
    assert "completion action is available" not in prompt
    assert "unless the observation clearly satisfies" in prompt
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


def test_completion_pre_repair_template_targets_buy_now():
    verification = {
        "is_error": True,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change strategy.",
        "avoid_action": "click[b09npml43m]",
    }
    record = {
        "step": 13,
        "raw_action": "click[b09npml43m]",
        "executed_action": "click[b09npml43m]",
    }
    prompt = format_pre_repair_hint_for_agent(
        build_repair_hint(verification, "pre", record),
        prompt_strength="completion",
    )
    assert "stalled product/option repeat" in prompt
    assert "Buy Now is visible" in prompt
    assert "output click[buy now]" in prompt
    assert "same navigation/search action" not in prompt


def test_completion_post_hint_template_targets_completion_without_metadata_leak():
    verification = {
        "is_error": True,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change strategy.",
        "avoid_action": "click[b09npml43m]",
    }
    record = {
        "step": 12,
        "raw_action": "click[b09npml43m]",
        "executed_action": "click[b09npml43m]",
        "post_check": {"repeated_behavior_risk": True},
    }
    hint = build_repair_hint(verification, "post", record)
    hint["hint_style"] = "completion"
    prompt = format_hint_for_agent(hint)
    assert "Buy Now is visible" in prompt
    assert "choose click[buy now]" in prompt
    assert '"hint_style"' not in prompt
    assert "policy_decision" not in prompt


def test_soft_local_post_hint_protects_needed_repeats():
    verification = {
        "is_error": True,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change strategy.",
        "avoid_action": "click[x-large]",
    }
    record = {
        "step": 8,
        "raw_action": "click[x-large]",
        "executed_action": "click[x-large]",
        "post_check": {"repeated_behavior_risk": True},
    }
    hint = build_repair_hint(verification, "post", record)
    hint["hint_style"] = "soft"
    prompt = format_hint_for_agent(hint)
    assert "Do not force a strategy change" in prompt
    assert "if this repeat is still needed" in prompt
    assert "avoid repeating it: click[x-large]" in prompt



def test_late_budget_post_hint_prioritizes_finishing_without_metadata_leak():
    verification = {
        "is_error": True,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change strategy.",
        "avoid_action": "click[next >]",
    }
    record = {
        "step": 13,
        "raw_action": "click[next >]",
        "executed_action": "click[next >]",
        "post_check": {"repeated_behavior_risk": True},
    }
    hint = build_repair_hint(verification, "post", record)
    hint["hint_style"] = "late"
    hint["policy_decision"] = {"remaining_steps": 1, "budget_level": "final"}
    prompt = format_hint_for_agent(hint)
    assert "step budget is almost exhausted" in prompt
    assert "You have 1 action(s) left" in prompt
    assert "finalization, verification, or commit action" in prompt
    assert "Do not repeat this action" in prompt
    assert "policy_decision" not in prompt
    assert "budget_level" not in prompt


def test_late_budget_pre_repair_template_is_valid():
    verification = {
        "is_error": True,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change strategy.",
        "avoid_action": "search[old]",
    }
    record = {"step": 14, "raw_action": "search[old]"}
    prompt = format_pre_repair_hint_for_agent(
        build_repair_hint(verification, "pre", record),
        prompt_strength="late",
    )
    assert "step budget is almost exhausted" in prompt
    assert "finish or directly advance" in prompt
    assert "Output only the action" in prompt



def test_task_aware_post_hint_uses_checklist_without_metadata_leak():
    verification = {
        "is_error": True,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change strategy.",
        "avoid_action": "click[details]",
    }
    record = {
        "step": 9,
        "raw_action": "click[details]",
        "executed_action": "click[details]",
        "post_check": {"repeated_behavior_risk": True},
    }
    hint = build_repair_hint(verification, "post", record)
    hint["hint_style"] = "task_late"
    hint["policy_decision"] = {
        "remaining_steps": 2,
        "budget_level": "low",
        "completion_candidates": ["Submit"],
        "task_progress": "task_evidence_visible",
    }
    prompt = format_hint_for_agent(hint)
    assert "Task-local checklist" in prompt
    assert "You have 2 action(s) left" in prompt
    assert "A visible finalization or verification action includes: Submit" in prompt
    assert "Do not repeat this action unless it is the only valid completing action: click[details]." in prompt
    assert "policy_decision" not in prompt
    assert "budget_level" not in prompt
    assert "task_progress" not in prompt


def test_task_aware_pre_repair_hint_uses_checklist():
    verification = {
        "is_error": True,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change strategy.",
        "avoid_action": "search[old]",
    }
    record = {"step": 12, "raw_action": "search[old]"}
    hint = build_repair_hint(verification, "pre", record)
    hint["policy_decision"] = {"remaining_steps": 2, "completion_candidates": ["Done"]}
    prompt = format_pre_repair_hint_for_agent(hint, prompt_strength="task_late")
    assert "Task-local checklist before choosing the next action" in prompt
    assert "You have 2 action(s) left" in prompt
    assert "Done" in prompt
    assert "Output only the action" in prompt


def test_finish_guarded_post_hint_is_generic_and_guarded():
    verification = {
        "is_error": True,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change strategy.",
        "avoid_action": "click[details]",
    }
    record = {
        "step": 8,
        "raw_action": "click[details]",
        "executed_action": "click[details]",
        "post_check": {"repeated_behavior_risk": True},
    }
    hint = build_repair_hint(verification, "post", record)
    hint["hint_style"] = "finish_guarded"
    hint["policy_decision"] = {"completion_candidates": ["Submit"]}
    prompt = format_hint_for_agent(hint)
    assert "Submit" in prompt
    assert "task requirements appear satisfied" in prompt
    assert "satisfies, verifies, or commits a missing requirement" in prompt
    assert "Buy Now is visible" not in prompt
    assert "policy_decision" not in prompt


def test_standard_loop_hint_does_not_push_completion_action():
    verification = {
        "is_error": True,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change strategy.",
        "avoid_action": "click[next >]",
    }
    record = {
        "step": 3,
        "raw_action": "click[next >]",
        "executed_action": "click[next >]",
        "post_check": {"repeated_behavior_risk": True},
    }
    hint = build_repair_hint(verification, "post", record)
    prompt = format_hint_for_agent(hint)
    assert "completion action is available" not in prompt
    assert "unless the observation clearly satisfies" in prompt


def test_budget_pressure_hint_is_guarded_and_metadata_free():
    hint = {
        "stage": "post",
        "source_step": 13,
        "error_type": "budget_pressure",
        "repair_hint": "",
        "avoid_action": None,
        "action_under_check": "click[details]",
        "post_check": {},
        "policy_decision": {
            "remaining_steps": 1,
            "budget_level": "final",
            "completion_candidates": ["Submit"],
            "finalization_type": "commit",
        },
        "hint_style": "budget_finish",
    }
    prompt = format_hint_for_agent(hint)
    assert "step budget is almost exhausted" in prompt
    assert "Do not start broad exploration" in prompt
    assert "Submit" in prompt
    assert "valid finalization action is available" in prompt
    assert "directly satisfies, verifies, or commits" in prompt
    assert "policy_decision" not in prompt
    assert "budget_level" not in prompt


def test_budget_pressure_hint_supports_terminal_verification():
    hint = {
        "stage": "post",
        "source_step": 13,
        "error_type": "budget_pressure",
        "repair_hint": "",
        "avoid_action": None,
        "action_under_check": "pytest",
        "post_check": {},
        "policy_decision": {
            "remaining_steps": 1,
            "completion_candidates": ["pytest tests/test_app.py"],
            "finalization_type": "verify",
        },
        "hint_style": "budget_finish",
    }
    prompt = format_hint_for_agent(hint)
    assert "pytest tests/test_app.py" in prompt
    assert "validation, test, or check" in prompt
    assert "Buy Now" not in prompt


def test_task_soft_loop_hint_is_generic_and_metadata_free():
    hint = {
        "stage": "post",
        "source_step": 4,
        "error_type": "loop_or_repetition",
        "repair_hint": "Change only if needed.",
        "avoid_action": "click[details]",
        "action_under_check": "click[details]",
        "post_check": {"repeated_behavior_risk": True},
        "policy_decision": {
            "prompt_strength": "task_soft",
            "task_progress": "no_task_evidence_visible",
            "completion_candidates": ["Submit"],
        },
        "hint_style": "task_soft",
    }
    prompt = format_hint_for_agent(hint)
    assert "necessary local repeat" in prompt
    assert "Submit" in prompt
    assert "Buy Now" not in prompt
    assert "policy_decision" not in prompt
    assert "task_progress" not in prompt
