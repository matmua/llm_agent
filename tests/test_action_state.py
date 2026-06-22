from state.action_state import (
    build_fallback_state,
    expected_effects_for_action,
    observed_effects,
)


def test_commit_state_tracks_missing_and_known_requirements():
    state = build_fallback_state(
        task_instruction="Instruction: Find me headphones with brand: Acme and price lower than $50.",
        observation="Instruction: Find me headphones [SEP] Acme Headphones [SEP] Price: $39.99 [SEP] Brand: Acme [SEP] buy now",
        available_actions={"has_search_bar": False, "clickables": ["buy now"]},
        raw_action="click[buy now]",
        step_id=2,
    )

    action = state.action_under_check
    assert action.action_type == "commit"
    assert "current_product exists" in action.satisfied_requirements
    assert not action.conflicting_requirements
    assert any("request.price_max" in item for item in action.satisfied_requirements)


def test_commit_state_marks_conflicting_price():
    state = build_fallback_state(
        task_instruction="Instruction: Find me headphones with brand: Acme and price lower than $50.",
        observation="Instruction: Find me headphones [SEP] Acme Headphones [SEP] Price: $79.99 [SEP] Brand: Acme [SEP] buy now",
        available_actions={"has_search_bar": False, "clickables": ["buy now"]},
        raw_action="click[buy now]",
        step_id=3,
    )

    assert state.action_under_check.pre_error
    assert any("price_max" in item for item in state.action_under_check.conflicting_requirements)


def test_expected_and_observed_effect_helpers():
    assert "episode done" in expected_effects_for_action("click[buy now]")
    observed = observed_effects(
        before="Search page",
        after="Search results for headphones",
        reward=0.0,
        done=False,
        before_available={"has_search_bar": True, "clickables": []},
        after_available={"has_search_bar": True, "clickables": ["Acme Headphones"]},
    )
    assert "observation changed" in observed
    assert "search results visible" in observed
