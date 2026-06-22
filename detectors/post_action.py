"""Post-action detector with warning/error separation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from state.action_state import (
    ActionCentricState,
    PostCheck,
    expected_effects_for_action,
    observed_effects,
)


@dataclass
class PostActionReport:
    post_warning: bool = False
    post_error: bool = False
    repair_trigger: bool = False
    categories: list[str] = field(default_factory=list)
    reason: str = ""
    expected_effect: list[str] = field(default_factory=list)
    observed_effect: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_warning": self.post_warning,
            "post_error": self.post_error,
            "repair_trigger": self.repair_trigger,
            "categories": self.categories,
            "reason": self.reason,
            "expected_effect": self.expected_effect,
            "observed_effect": self.observed_effect,
        }

    def to_post_check(self) -> PostCheck:
        return PostCheck(
            expected_effect=self.expected_effect,
            observed_effect=self.observed_effect,
            matched=not self.post_error,
            post_warning=self.post_warning,
            post_error=self.post_error,
            repair_trigger=self.repair_trigger,
            reason=self.reason,
        )


class PostActionDetector:
    def detect(
        self,
        state_before: ActionCentricState,
        raw_action: str,
        observation_before: str,
        observation_after: str,
        state_after: ActionCentricState,
        pre_report: dict[str, Any],
        reward: float,
        done: bool,
        previous_step_logs: list[dict[str, Any]] | None = None,
        before_available: dict[str, Any] | None = None,
        after_available: dict[str, Any] | None = None,
        episode_ending: bool = False,
    ) -> PostActionReport:
        previous_step_logs = previous_step_logs or []
        expected = expected_effects_for_action(raw_action)
        observed = observed_effects(
            observation_before,
            observation_after,
            reward=reward,
            done=done,
            before_available=before_available,
            after_available=after_available,
        )
        categories: list[str] = []
        warning = False
        error = False

        no_effect = "observation changed" not in observed and "available actions changed" not in observed
        unexpected = _unexpected_transition(state_before, state_after, expected, observed, done)
        explicit_conflicts = list(state_after.action_under_check.conflicting_requirements)

        if no_effect:
            if _repeated(previous_step_logs, raw_action, "single_no_effect"):
                categories.append("repeated_no_effect")
                error = True
            else:
                categories.append("single_no_effect")
                warning = True
        if unexpected:
            if _repeated(previous_step_logs, raw_action, "single_unexpected_transition"):
                categories.append("repeated_unexpected_transition")
                error = True
            else:
                categories.append("single_unexpected_transition")
                warning = True
        if explicit_conflicts:
            categories.append("explicit_conflict")
            error = True

        action_type = state_before.action_under_check.action_type
        preventable = (
            (action_type == "commit" or raw_action.lower() == "click[buy now]")
            and (done or episode_ending)
            and reward <= 0
            and (
                bool(pre_report.get("missing_requirements"))
                or bool(pre_report.get("conflicting_requirements"))
            )
        )
        if preventable:
            categories.append("preventable_failure")
            error = True

        missing_evidence = (
            action_type == "commit"
            and (
                bool(pre_report.get("missing_requirements"))
                or any(rel.status == "missing_evidence" for rel in state_after.relations)
            )
        )
        if missing_evidence and not error:
            categories.append("missing_evidence")
            warning = True

        repair_trigger = bool(
            error
            and any(
                item in categories
                for item in (
                    "explicit_conflict",
                    "repeated_no_effect",
                    "repeated_unexpected_transition",
                    "preventable_failure",
                )
            )
        )
        reason = _reason(categories, warning, error)
        return PostActionReport(
            post_warning=bool(warning or error),
            post_error=error,
            repair_trigger=repair_trigger,
            categories=_unique(categories),
            reason=reason,
            expected_effect=expected,
            observed_effect=observed,
        )


def _unexpected_transition(
    state_before: ActionCentricState,
    state_after: ActionCentricState,
    expected: list[str],
    observed: list[str],
    done: bool,
) -> bool:
    action_type = state_before.action_under_check.action_type
    if action_type == "commit":
        return not done
    if action_type == "explore":
        return "search results visible" not in observed and "observation changed" not in observed
    if action_type == "inspect":
        return not any(item in observed for item in ("product page visible", "observation changed", "available actions changed"))
    if action_type == "backtrack":
        return not any(item in observed for item in ("search results visible", "observation changed", "available actions changed"))
    return False


def _repeated(previous_step_logs: list[dict[str, Any]], raw_action: str, previous_category: str) -> bool:
    if not previous_step_logs:
        return False
    previous = previous_step_logs[-1]
    previous_action = str(previous.get("raw_action", ""))
    previous_categories = previous.get("post_report", {}).get("categories", [])
    if previous_action == raw_action and previous_category in previous_categories:
        return True
    previous_type = previous.get("state_before", {}).get("action_under_check", {}).get("action_type")
    current_type = _action_type(raw_action)
    return bool(previous_type and previous_type == current_type and previous_category in previous_categories)


def _action_type(action: str) -> str:
    lowered = action.strip().lower()
    if lowered.startswith("search["):
        return "explore"
    if lowered.startswith("click[buy now]"):
        return "commit"
    if lowered.startswith("click[back to search]"):
        return "backtrack"
    if lowered.startswith("click["):
        return "inspect"
    return "invalid"


def _reason(categories: list[str], warning: bool, error: bool) -> str:
    if not categories:
        return "No post-action issue detected."
    if error:
        return "Post-action error: " + ", ".join(categories)
    if warning:
        return "Post-action warning only: " + ", ".join(categories)
    return "No post-action issue detected."


def _unique(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
