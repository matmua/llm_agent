from detectors.post_action import PostActionDetector
from detectors.pre_action import PreActionDetector
from state.action_state import build_fallback_state


def test_single_no_effect_is_warning_only():
    state = build_fallback_state(
        task_instruction="Instruction: Find me headphones.",
        observation="Search page",
        available_actions={"has_search_bar": True, "clickables": []},
        raw_action="search[headphones]",
        step_id=0,
    )
    pre_report = PreActionDetector().detect(
        "search[headphones]",
        {"has_search_bar": True, "clickables": []},
        state,
    )

    report = PostActionDetector().detect(
        state_before=state,
        raw_action="search[headphones]",
        observation_before="Search page",
        observation_after="Search page",
        state_after=state,
        pre_report=pre_report.to_dict(),
        reward=0.0,
        done=False,
        before_available={"has_search_bar": True, "clickables": []},
        after_available={"has_search_bar": True, "clickables": []},
    )

    assert report.post_warning
    assert not report.post_error
    assert "single_no_effect" in report.categories


def test_repeated_no_effect_promotes_to_error():
    state = build_fallback_state(
        task_instruction="Instruction: Find me headphones.",
        observation="Search page",
        available_actions={"has_search_bar": True, "clickables": []},
        raw_action="search[headphones]",
        step_id=0,
    )
    pre_report = PreActionDetector().detect(
        "search[headphones]",
        {"has_search_bar": True, "clickables": []},
        state,
    )
    first = PostActionDetector().detect(
        state_before=state,
        raw_action="search[headphones]",
        observation_before="Search page",
        observation_after="Search page",
        state_after=state,
        pre_report=pre_report.to_dict(),
        reward=0.0,
        done=False,
        before_available={"has_search_bar": True, "clickables": []},
        after_available={"has_search_bar": True, "clickables": []},
    )
    previous_log = {
        "raw_action": "search[headphones]",
        "state_before": state.to_dict(),
        "post_report": first.to_dict(),
    }
    second = PostActionDetector().detect(
        state_before=state,
        raw_action="search[headphones]",
        observation_before="Search page",
        observation_after="Search page",
        state_after=state,
        pre_report=pre_report.to_dict(),
        reward=0.0,
        done=False,
        previous_step_logs=[previous_log],
        before_available={"has_search_bar": True, "clickables": []},
        after_available={"has_search_bar": True, "clickables": []},
    )

    assert second.post_error
    assert second.repair_trigger
    assert "repeated_no_effect" in second.categories


def test_failed_commit_after_pre_missing_is_preventable_failure():
    before = build_fallback_state(
        task_instruction="Instruction: Find me headphones with price lower than $30.",
        observation="Instruction: Find me headphones [SEP] Budget Headphones [SEP] Brand: Acme [SEP] buy now",
        available_actions={"has_search_bar": False, "clickables": ["buy now"]},
        raw_action="click[buy now]",
        step_id=2,
    )
    after = build_fallback_state(
        task_instruction="Instruction: Find me headphones with price lower than $30.",
        observation="Instruction: Find me headphones [SEP] Done [SEP] Purchased: Budget Headphones [SEP] Score: 0.0",
        available_actions={"has_search_bar": False, "clickables": []},
        raw_action="click[buy now]",
        step_id=2,
    )
    pre_report = PreActionDetector().detect(
        "click[buy now]",
        {"has_search_bar": False, "clickables": ["buy now"]},
        before,
    )

    report = PostActionDetector().detect(
        state_before=before,
        raw_action="click[buy now]",
        observation_before="product page buy now",
        observation_after="done score 0.0",
        state_after=after,
        pre_report=pre_report.to_dict(),
        reward=0.0,
        done=True,
        before_available={"has_search_bar": False, "clickables": ["buy now"]},
        after_available={"has_search_bar": False, "clickables": []},
        episode_ending=True,
    )

    assert report.post_error
    assert report.repair_trigger
    assert "preventable_failure" in report.categories
