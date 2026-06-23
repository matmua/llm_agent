from intervention.repair_hint import (
    build_repair_hint,
    format_hint_for_agent,
    mark_hint_outcome,
    should_apply_pre_repair,
    should_create_post_hint,
)


def test_repair_hint_decisions_and_loop_template():
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
    }
    assert should_apply_pre_repair(verification, repair_enabled=True) is True
    assert should_apply_pre_repair(verification, repair_enabled=False) is False
    assert should_create_post_hint(verification, repair_enabled=True) is True

    hint = build_repair_hint(verification, "post", record)
    prompt = format_hint_for_agent(hint)
    assert "[Risk-control hint for the next action only]" in prompt
    assert "Avoid repeating this action: click[next >]." in prompt
    assert mark_hint_outcome(hint, "click[next >]")["followed"] is False
    assert mark_hint_outcome(hint, "click[item]")["followed"] is True


def test_repair_hint_without_avoid_action_uses_strategy_template():
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
    }
    hint = build_repair_hint(verification, "pre", record)
    prompt = format_hint_for_agent(hint)
    assert "[Risk-control hint for the current action only]" in prompt
    assert "Do not continue the same strategy." in prompt
    assert "Avoid repeating this action" not in prompt
    assert mark_hint_outcome(hint, "click[item]")["followed"] is False

