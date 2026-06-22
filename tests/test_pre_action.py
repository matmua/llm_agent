from detectors.pre_action import PreActionDetector
from state.action_state import build_fallback_state


def test_missing_evidence_is_warning_not_error():
    state = build_fallback_state(
        task_instruction="Instruction: Find me shoes with brand: Acme and price lower than $30.",
        observation="Instruction: Find me shoes [SEP] Acme Shoes [SEP] Brand: Acme [SEP] buy now",
        available_actions={"has_search_bar": False, "clickables": ["buy now"]},
        raw_action="click[buy now]",
        step_id=1,
    )

    report = PreActionDetector().detect(
        raw_action="click[buy now]",
        available_actions={"has_search_bar": False, "clickables": ["buy now"]},
        state=state,
    )

    assert report.pre_warning
    assert not report.pre_error
    assert "missing_evidence" in report.categories


def test_explicit_conflict_is_error_and_repair_trigger_for_commit():
    state = build_fallback_state(
        task_instruction="Instruction: Find me shoes with brand: Acme and price lower than $30.",
        observation="Instruction: Find me shoes [SEP] Acme Shoes [SEP] Price: $99.99 [SEP] Brand: Acme [SEP] buy now",
        available_actions={"has_search_bar": False, "clickables": ["buy now"]},
        raw_action="click[buy now]",
        step_id=1,
    )

    report = PreActionDetector().detect(
        raw_action="click[buy now]",
        available_actions={"has_search_bar": False, "clickables": ["buy now"]},
        state=state,
    )

    assert report.pre_error
    assert report.repair_trigger
    assert "explicit_conflict" in report.categories


def test_repeated_invalid_action_promotes_to_error():
    state = build_fallback_state(
        task_instruction="Instruction: Find me shoes.",
        observation="Instruction: Find me shoes [SEP] Search page",
        available_actions={"has_search_bar": True, "clickables": []},
        raw_action="click[missing]",
        step_id=0,
    )
    detector = PreActionDetector()
    first = detector.detect("click[missing]", {"has_search_bar": True, "clickables": []}, state)
    second = detector.detect(
        "click[missing]",
        {"has_search_bar": True, "clickables": []},
        state,
        previous_reports=[first.to_dict()],
    )

    assert first.pre_warning
    assert not first.pre_error
    assert second.pre_error
    assert "repeated_invalid_action" in second.categories
