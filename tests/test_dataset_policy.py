from typing import Optional

from intervention.action_space import candidate_action_texts
from intervention.dataset_policy import (
    SimpleBudgetPolicy,
    SimpleBudgetV2Policy,
    SimpleBudgetV4Policy,
    StepBudgetPolicy,
    TaskAwarePolicy,
    WebShopPolicy,
    budget_level,
    budget_level_for_task,
    classify_webshop_action,
    get_dataset_policy,
    infer_finalization_type,
    visible_completion_candidates,
)
from intervention.repair_hint import (
    build_repair_hint,
    format_pre_repair_hint_for_agent,
)
from shadow.parser import action_signature, parse_action


def _record(action: str) -> dict:
    parsed = parse_action(action)
    return {
        "step": 3,
        "raw_action": action,
        "original_parsed_action": parsed,
        "original_action_signature": action_signature(parsed),
        "parsed_action": parsed,
        "type": parsed["type"],
        "params": parsed["params"],
        "context_before": "ctx_product",
        "action_signature": action_signature(parsed),
    }


def _verification(error_type: str = "loop_or_repetition", avoid_action: Optional[str] = None) -> dict:
    return {
        "is_error": True,
        "error_type": error_type,
        "confidence": 0.95,
        "repair_hint": "Change strategy.",
        "avoid_action": avoid_action,
    }


def _shadow_with_repeated_no_delta(record: dict, count: int = 3) -> dict:
    return {
        "actions": [
            {
                "context_before": record["context_before"],
                "action_signature": record["action_signature"],
                "post_check": {"visible_delta": False, "info_gain": False},
            }
            for _ in range(count)
        ]
    }


def test_webshop_policy_strong_repairs_navigation_repeat():
    policy = WebShopPolicy()
    record = _record("click[next >]")
    decision = policy.decide_pre_repair(record, _verification(avoid_action="click[next >]"), "", {})
    assert classify_webshop_action(record) == "navigation"
    assert decision.mode == "pre_repair"
    assert decision.prompt_strength == "strong"
    assert decision.protected is False

    hint = build_repair_hint(_verification(avoid_action="click[next >]"), "pre", record)
    prompt = format_pre_repair_hint_for_agent(hint, decision.prompt_strength)
    assert "Do not output this same navigation/search action again: click[next >]." in prompt


def test_webshop_policy_strong_repairs_repeated_search():
    policy = WebShopPolicy()
    record = _record("search[blue pillow]")
    decision = policy.decide_pre_repair(record, _verification(avoid_action="search[blue pillow]"), "", {})
    assert classify_webshop_action(record) == "search"
    assert decision.mode == "pre_repair"
    assert decision.prompt_strength == "strong"


def test_webshop_policy_protects_product_option_and_completion_repeats_by_default():
    policy = WebShopPolicy()
    for action, action_class in [
        ("click[b09npml43m]", "product"),
        ("click[x-large]", "option"),
        ("click[buy now]", "completion"),
    ]:
        record = _record(action)
        decision = policy.decide_pre_repair(record, _verification(avoid_action=action), "", {})
        assert classify_webshop_action(record) == action_class
        assert decision.mode == "record_only"
        assert decision.reason == "webshop_protected_local_repeat"
        assert decision.protected is True


def test_webshop_policy_completion_repairs_product_repeat_when_stuck_and_buy_now_visible():
    policy = WebShopPolicy()
    record = _record("click[b09npml43m]")
    decision = policy.decide_pre_repair(
        record,
        _verification(avoid_action="click[b09npml43m]"),
        "Product page [SEP] Buy Now",
        {"clickables": ["Buy Now", "large"]},
        shadow_state=_shadow_with_repeated_no_delta(record, count=3),
    )
    assert decision.mode == "pre_repair"
    assert decision.reason == "webshop_protected_local_repeat_stuck_completion_visible"
    assert decision.prompt_strength == "completion"
    assert decision.stuck is True
    assert decision.completion_visible is True

    hint = build_repair_hint(_verification(avoid_action="click[b09npml43m]"), "pre", record)
    prompt = format_pre_repair_hint_for_agent(hint, decision.prompt_strength)
    assert "Buy Now is visible" in prompt
    assert "output click[buy now]" in prompt


def test_webshop_policy_keeps_product_repeat_protected_before_stuck_threshold():
    policy = WebShopPolicy()
    record = _record("click[b09npml43m]")
    decision = policy.decide_pre_repair(
        record,
        _verification(avoid_action="click[b09npml43m]"),
        "Product page [SEP] Buy Now",
        {"clickables": ["Buy Now"]},
        shadow_state=_shadow_with_repeated_no_delta(record, count=2),
    )
    assert decision.mode == "record_only"
    assert decision.protected is True
    assert decision.stuck is False


def test_webshop_policy_completion_post_hint_for_stuck_local_repeat():
    policy = WebShopPolicy()
    record = _record("click[b09npml43m]")
    record["post_check"] = {
        "same_action_no_visible_delta_count": 3,
        "repeated_behavior_risk": True,
        "visible_delta": False,
    }
    decision = policy.decide_post_hint(
        record,
        _verification(avoid_action="click[b09npml43m]"),
        "Product page [SEP] Buy Now",
        {"clickables": ["Buy Now"]},
    )
    assert decision.mode == "hint"
    assert decision.prompt_strength == "completion"
    assert decision.stuck is True


def test_webshop_policy_soft_post_hint_for_non_stuck_local_repeat():
    policy = WebShopPolicy()
    record = _record("click[x-large]")
    record["post_check"] = {
        "same_action_no_visible_delta_count": 1,
        "repeated_behavior_risk": True,
        "visible_delta": False,
    }
    decision = policy.decide_post_hint(
        record,
        _verification(avoid_action="click[x-large]"),
        "Product page [SEP] Buy Now",
        {"clickables": ["Buy Now"]},
    )
    assert decision.mode == "hint"
    assert decision.prompt_strength == "soft"
    assert decision.protected is True


def test_webshop_policy_still_repairs_format_errors_with_standard_hint():
    policy = WebShopPolicy()
    record = _record("I choose the first product")
    decision = policy.decide_pre_repair(record, _verification(error_type="format_error"), "", {})
    assert decision.mode == "pre_repair"
    assert decision.prompt_strength == "standard"


def test_auto_policy_resolves_webshop_for_official_env():
    assert get_dataset_policy("auto", requested_env="official").name == "webshop"



def test_budget_level_thresholds():
    assert budget_level(None) == "unknown"
    assert budget_level(1) == "final"
    assert budget_level(3) == "low"
    assert budget_level(4) == "medium"
    assert budget_level(7) == "high"


def test_webshop_policy_late_post_hint_for_low_budget_navigation_repeat():
    policy = WebShopPolicy()
    record = _record("click[next >]")
    record["post_check"] = {
        "same_action_no_visible_delta_count": 3,
        "repeated_behavior_risk": True,
        "visible_delta": False,
    }
    decision = policy.decide_post_hint(
        record,
        _verification(avoid_action="click[next >]"),
        "Search page [SEP] Next >",
        {"clickables": ["next >", "b09example"]},
        remaining_steps=2,
    )
    assert decision.mode == "hint"
    assert decision.prompt_strength == "late"
    assert decision.reason == "webshop_low_budget_standard_post_hint"
    assert decision.remaining_steps == 2
    assert decision.budget_level == "low"


def test_webshop_policy_low_budget_local_repeat_with_buy_now_uses_completion_hint():
    policy = WebShopPolicy()
    record = _record("click[x-large]")
    record["post_check"] = {
        "same_action_no_visible_delta_count": 1,
        "repeated_behavior_risk": True,
        "visible_delta": False,
    }
    decision = policy.decide_post_hint(
        record,
        _verification(avoid_action="click[x-large]"),
        "Product page [SEP] Buy Now",
        {"clickables": ["Buy Now", "x-large"]},
        remaining_steps=1,
    )
    assert decision.mode == "hint"
    assert decision.reason == "webshop_low_budget_local_repeat_completion_visible"
    assert decision.prompt_strength == "completion"
    assert decision.completion_visible is True
    assert decision.budget_level == "final"



def test_step_budget_policy_does_not_use_webshop_action_semantics_for_post_hint():
    policy = StepBudgetPolicy()
    record = _record("click[b09npml43m]")
    record["post_check"] = {
        "same_action_no_visible_delta_count": 3,
        "repeated_behavior_risk": True,
        "visible_delta": False,
    }
    decision = policy.decide_post_hint(
        record,
        _verification(avoid_action="click[b09npml43m]"),
        "Product page [SEP] Buy Now",
        {"clickables": ["Buy Now"]},
        remaining_steps=2,
    )
    assert decision.mode == "hint"
    assert decision.reason == "step_budget_low_budget_post_hint"
    assert decision.prompt_strength == "late"
    assert decision.action_class == "unknown"
    assert decision.completion_visible is False
    assert decision.stuck is False
    assert decision.budget_level == "low"


def test_step_budget_policy_records_pre_error_until_low_budget():
    policy = StepBudgetPolicy()
    record = _record("click[next >]")
    early = policy.decide_pre_repair(
        record,
        _verification(avoid_action="click[next >]"),
        "Search page",
        {"clickables": ["next >"]},
        remaining_steps=8,
    )
    late = policy.decide_pre_repair(
        record,
        _verification(avoid_action="click[next >]"),
        "Search page",
        {"clickables": ["next >"]},
        remaining_steps=2,
    )
    assert early.mode == "record_only"
    assert early.prompt_strength == "none"
    assert early.action_class == "unknown"
    assert late.mode == "pre_repair"
    assert late.prompt_strength == "late"
    assert late.reason == "step_budget_low_budget_verified_pre_error"


def test_get_dataset_policy_resolves_step_budget_alias():
    assert get_dataset_policy("step_budget").name == "step_budget"
    assert get_dataset_policy("step").name == "step_budget"



def test_task_aware_policy_uses_fractional_budget_without_webshop_semantics():
    policy = TaskAwarePolicy()
    record = _record("click[next >]")
    early = policy.decide_pre_repair(
        record,
        _verification(avoid_action="click[next >]"),
        "Search page",
        {"clickables": ["next >", "details"]},
        remaining_steps=20,
        max_steps=50,
        task="Find the blue waterproof backpack",
    )
    late = policy.decide_pre_repair(
        record,
        _verification(avoid_action="click[next >]"),
        "Search page",
        {"clickables": ["next >", "details"]},
        remaining_steps=9,
        max_steps=50,
        task="Find the blue waterproof backpack",
    )
    assert budget_level_for_task(20, 50) == "medium"
    assert budget_level_for_task(9, 50) == "low"
    assert early.mode == "record_only"
    assert early.action_class == "unknown"
    assert early.task_progress in {"unknown", "no_task_evidence_visible", "task_evidence_visible", "task_aligned_action"}
    assert late.mode == "pre_repair"
    assert late.prompt_strength == "task_late"
    assert late.budget_fraction == 0.18


def test_task_aware_policy_post_hint_adds_task_local_completion_candidates():
    policy = TaskAwarePolicy()
    record = _record("click[details]")
    record["post_check"] = {
        "same_action_no_visible_delta_count": 3,
        "repeated_behavior_risk": True,
        "visible_delta": False,
    }
    decision = policy.decide_post_hint(
        record,
        _verification(avoid_action="click[details]"),
        "Current item satisfies the requested constraints.",
        {"clickables": ["Submit", "details"]},
        remaining_steps=2,
        max_steps=15,
        task="Select an item that satisfies the requested constraints",
    )
    assert decision.mode == "hint"
    assert decision.prompt_strength == "task_late"
    assert decision.reason == "task_aware_low_budget_post_hint"
    assert decision.action_class == "unknown"
    assert decision.completion_visible is True
    assert decision.completion_candidates == ("Submit",)


def test_visible_completion_candidates_is_generic_not_webshop_only():
    assert visible_completion_candidates("", {"clickables": ["Finish", "Back"]}) == ("Finish",)
    assert visible_completion_candidates("Ready to submit answer", {"clickables": ["Back"]}) == ("submit",)


def test_finalization_keywords_do_not_match_substrings():
    assert visible_completion_candidates("", {"clickables": ["bright white", "profile"]}) == ()
    assert infer_finalization_type(
        "Find a bright white shirt",
        "Options include bright white and profile fit",
        {"clickables": ["bright white", "profile"]},
    ) == "last_gap"

def test_finalization_type_ignores_non_completion_tool_names():
    assert visible_completion_candidates("Need more evidence", {"tools": [{"tool": "read_file"}]}) == ()
    assert (
        infer_finalization_type(
            "Inspect the repository and identify the issue",
            "Need one more piece of evidence.",
            {"tools": [{"tool": "read_file"}]},
        )
        == "last_gap"
    )


def test_get_dataset_policy_resolves_task_aware_alias():
    assert get_dataset_policy("task_aware").name == "task_aware"
    assert get_dataset_policy("task").name == "task_aware"



def test_task_aware_policy_keeps_standard_post_hint_before_low_budget():
    policy = TaskAwarePolicy()
    record = _record("click[details]")
    record["post_check"] = {"repeated_behavior_risk": True, "visible_delta": False}
    decision = policy.decide_post_hint(
        record,
        _verification(avoid_action="click[details]"),
        "Observation with relevant evidence",
        {"clickables": ["details", "Submit"]},
        remaining_steps=8,
        max_steps=15,
        task="Select the item that satisfies the constraints",
    )
    assert decision.mode == "hint"
    assert decision.prompt_strength == "standard"
    assert decision.reason == "task_aware_standard_post_hint"
    assert decision.completion_candidates == ("Submit",)



def test_auto_policy_resolves_simple_budget_for_unknown_env():
    assert get_dataset_policy("auto", requested_env="unknown_env").name == "simple_budget"


def test_generic_policy_does_not_use_webshop_action_classes():
    policy = get_dataset_policy("generic")
    record = _record("click[b09npml43m]")
    decision = policy.decide_post_hint(
        record,
        _verification(avoid_action="click[b09npml43m]"),
        "Observation",
        {"clickables": ["b09npml43m"]},
        remaining_steps=2,
    )
    assert decision.action_class == "unknown"


def test_simple_budget_policy_uses_guarded_completion_only_when_stuck():
    policy = SimpleBudgetPolicy()
    record = _record("click[details]")
    record["post_check"] = {
        "same_action_no_visible_delta_count": 3,
        "repeated_behavior_risk": True,
        "visible_delta": False,
    }
    decision = policy.decide_post_hint(
        record,
        _verification(avoid_action="click[details]"),
        "The current page has a final submit button.",
        {"clickables": ["Submit", "details"]},
        remaining_steps=8,
    )
    assert decision.mode == "hint"
    assert decision.reason == "simple_budget_stalled_repeat_with_completion_candidate"
    assert decision.prompt_strength == "finish_guarded"
    assert decision.action_class == "unknown"
    assert decision.stuck is True
    assert decision.completion_visible is True
    assert decision.completion_candidates == ("Submit",)


def test_simple_budget_policy_keeps_standard_hint_before_stuck_threshold():
    policy = SimpleBudgetPolicy()
    record = _record("click[details]")
    record["post_check"] = {
        "same_action_no_visible_delta_count": 2,
        "repeated_behavior_risk": True,
        "visible_delta": False,
    }
    decision = policy.decide_post_hint(
        record,
        _verification(avoid_action="click[details]"),
        "The current page has a final submit button.",
        {"clickables": ["Submit", "details"]},
        remaining_steps=8,
    )
    assert decision.mode == "hint"
    assert decision.reason == "simple_budget_standard_post_hint"
    assert decision.prompt_strength == "standard"
    assert decision.completion_visible is True


def test_get_dataset_policy_resolves_simple_budget_alias():
    assert get_dataset_policy("simple_budget").name == "simple_budget"
    assert get_dataset_policy("simple").name == "simple_budget"
    assert get_dataset_policy("simple_budget_v2").name == "simple_budget_v2"
    assert get_dataset_policy("simple_budget_v3").name == "simple_budget"
    assert get_dataset_policy("simple_budget_v4").name == "simple_budget_v4"


def test_simple_budget_v2_has_no_final_completion_nudge():
    policy = SimpleBudgetV2Policy()
    decision = policy.decide_budget_hint(
        _record("click[details]"),
        "Ready to submit answer",
        {"clickables": ["Submit", "details"]},
        remaining_steps=1,
    )
    assert decision.mode == "skip"
    assert decision.reason == "budget_hint_disabled"
    assert decision.policy == "simple_budget_v2"


def test_simple_budget_policy_uses_late_prompt_for_low_budget_stuck_completion():
    policy = SimpleBudgetPolicy()
    record = _record("click[details]")
    record["post_check"] = {
        "same_action_no_visible_delta_count": 3,
        "repeated_behavior_risk": True,
        "visible_delta": False,
    }
    decision = policy.decide_post_hint(
        record,
        _verification(avoid_action="click[details]"),
        "The current page has a final submit button.",
        {"clickables": ["Submit", "details"]},
        remaining_steps=2,
    )
    assert decision.mode == "hint"
    assert decision.reason == "simple_budget_low_budget_stalled_repeat"
    assert decision.prompt_strength == "late"
    assert decision.stuck is True
    assert decision.completion_visible is True


def test_simple_budget_finalization_nudge_only_on_final_budget():
    policy = SimpleBudgetPolicy()
    record = _record("click[details]")
    final = policy.decide_budget_hint(
        record,
        "Ready to submit answer",
        {"clickables": ["Submit", "details"]},
        remaining_steps=1,
        max_steps=15,
    )
    early = policy.decide_budget_hint(
        record,
        "Ready to submit answer",
        {"clickables": ["Submit", "details"]},
        remaining_steps=2,
        max_steps=15,
    )
    assert final.mode == "hint"
    assert final.reason == "simple_budget_generic_finalization_nudge"
    assert final.prompt_strength == "budget_finish"
    assert final.completion_candidates == ("Submit",)
    assert final.finalization_type == "commit"
    assert early.mode == "skip"
    assert early.reason == "simple_budget_no_finalization_nudge"


def test_simple_budget_finalization_nudge_without_visible_candidate():
    policy = SimpleBudgetPolicy()
    decision = policy.decide_budget_hint(
        _record("click[details]"),
        "One direct action remains to satisfy the request.",
        {"clickables": ["details"]},
        remaining_steps=1,
        max_steps=15,
        task="Fix the issue",
    )
    assert decision.mode == "hint"
    assert decision.completion_visible is False
    assert decision.completion_candidates == ()
    assert decision.finalization_type == "last_gap"


def test_simple_budget_finalization_nudge_triggers_on_tight_fraction():
    policy = SimpleBudgetPolicy()
    decision = policy.decide_budget_hint(
        _record("click[details]"),
        "Run the smallest validation command now.",
        {"clickables": ["pytest tests/test_app.py"]},
        remaining_steps=2,
        max_steps=20,
        task="Fix the bug and run tests",
    )
    assert decision.mode == "hint"
    assert decision.budget_fraction == 0.1
    assert decision.finalization_type == "verify"
    assert decision.completion_candidates == ("pytest tests/test_app.py",)


def test_generic_budget_hint_is_disabled():
    policy = get_dataset_policy("generic")
    decision = policy.decide_budget_hint(
        _record("click[details]"),
        "Ready to submit answer",
        {"clickables": ["Submit"]},
        remaining_steps=1,
    )
    assert decision.mode == "skip"
    assert decision.reason == "budget_hint_disabled"


def test_simple_budget_v4_uses_generic_finalization_nudge():
    policy = SimpleBudgetV4Policy()
    decision = policy.decide_budget_hint(
        _record("click[details]"),
        "Run the smallest validation command now.",
        {"clickables": ["pytest tests/test_app.py"]},
        remaining_steps=1,
        max_steps=15,
        task="Fix the bug and run tests",
    )
    assert decision.mode == "hint"
    assert decision.policy == "simple_budget_v4"
    assert decision.reason == "simple_budget_generic_finalization_nudge"
    assert decision.prompt_strength == "budget_finish"
    assert decision.finalization_type == "verify"
    assert decision.completion_candidates == ("pytest tests/test_app.py",)


def test_simple_budget_v4_uses_v2_post_hint_logic():
    policy = SimpleBudgetV4Policy()
    record = _record("click[details]")
    record["post_check"] = {
        "same_action_no_visible_delta_count": 3,
        "repeated_behavior_risk": True,
        "visible_delta": False,
    }
    decision = policy.decide_post_hint(
        record,
        _verification(avoid_action="click[details]"),
        "The current page has a final submit button.",
        {"clickables": ["Submit", "details"]},
        remaining_steps=8,
        max_steps=15,
        task="Submit the correct answer",
    )
    assert decision.mode == "hint"
    assert decision.policy == "simple_budget_v4"
    assert decision.reason == "simple_budget_stalled_repeat_with_completion_candidate"
    assert decision.prompt_strength == "finish_guarded"
    assert decision.stuck is True


def test_simple_budget_v4_no_longer_uses_strict_verifier_prompt_override():
    policy = SimpleBudgetV4Policy()
    assert not hasattr(policy, "risk_verifier_system_prompt")


def test_candidate_action_texts_accepts_structured_tool_schemas():
    assert candidate_action_texts([{"tool": "read_file"}, "final_answer"]) == (
        "read_file",
        "final_answer",
    )
    assert candidate_action_texts(
        {"tools": {"read_file": {"description": "Read a file"}, "final_answer": {}}}
    ) == ("read_file", "final_answer")


def test_visible_completion_candidates_accepts_command_schema():
    assert visible_completion_candidates("", {"commands": ["pytest tests/test_app.py", "ls"]}) == (
        "pytest tests/test_app.py",
    )


def test_simple_budget_v4_handles_command_schema_without_webshop_clickables():
    policy = SimpleBudgetV4Policy()
    decision = policy.decide_budget_hint(
        _record("click[details]"),
        "Run the focused validation command now.",
        {"commands": ["pytest tests/test_app.py", "ls"]},
        remaining_steps=1,
        max_steps=15,
        task="Fix the bug and run tests",
    )
    assert decision.mode == "hint"
    assert decision.policy == "simple_budget_v4"
    assert decision.finalization_type == "verify"
    assert decision.completion_candidates == ("pytest tests/test_app.py",)


def test_simple_budget_v4_handles_function_tool_schema():
    policy = SimpleBudgetV4Policy()
    decision = policy.decide_budget_hint(
        _record("click[details]"),
        "The answer is ready.",
        {
            "tools": [
                {
                    "type": "function",
                    "function": {"name": "final_answer", "description": "Submit final answer"},
                }
            ]
        },
        remaining_steps=1,
        max_steps=15,
        task="Solve the task and submit the final answer",
    )
    assert decision.mode == "hint"
    assert decision.finalization_type == "commit"
    assert decision.completion_candidates == ("final_answer",)
